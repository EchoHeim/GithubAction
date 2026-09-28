#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Trending 周榜 -> DeepSeek 写推文 -> 飞书推送

一条流水线，每周六早 6 点（北京时间）跑一次：
    抓 GitHub Trending 近一周（since=weekly）热度最高的项目
    -> 拉元信息 + README -> DeepSeek 生成公众号推文 Markdown
    -> 落盘 articles/YYYY-Www.md + latest.md -> 推送到飞书群机器人

用法：
    python Trending/trending_article.py --dry-run      # 不调 LLM、不推送，只验证抓取+落盘
    python Trending/trending_article.py               # 全流程（默认 weekly）
    python Trending/trending_article.py --since daily --top 3 --no-push

环境变量：
    DEEPSEEK_API_KEY   必填（全流程时）。--dry-run 可缺省
    DEEPSEEK_BASE_URL  可选，默认 https://api.deepseek.com
    DEEPSEEK_MODEL     可选，留空则用 GET /models 自动探测（首选 deepseek-flash）
    DEEPSEEK_THINKING  可选，默认 0（关闭思考模式）。写推文不需要思维链
    DEEPSEEK_REASONING_EFFORT 可选，仅在开启思考模式时生效，默认 high
    FEISHU_WEBHOOK_URL 可选。缺省时只落盘不推送
    FEISHU_SIGN_KEY    可选，机器人开启"签名校验"时必填
    GH_TOKEN           可选，GitHub API 兜底/提额（每小时 60 -> 5000 次）

退出码：0 成功（含降级成功）；1 关键步骤失败
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- 常量配置

CST = timezone(timedelta(hours=8))  # 固定 +8，避免依赖系统 tzdata
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "articles"
LATEST = ROOT / "latest.md"

TRENDING_URL = "https://github.com/trending"
UA = "Mozilla/5.0 (compatible; TrendingBot/1.0; +https://github.com)"

README_MAX_CHARS = 12000   # 喂给模型的 README 截断长度
FEISHU_MD_LIMIT = 4500     # 飞书卡片 markdown 正文字符上限（留足 20KB 报文余量）
HTTP_TIMEOUT = 30
LLM_TIMEOUT = 120
LLM_RETRIES = 3

# /models 探测结果缓存（key: (base_url, api_key)），避免同一轮重复探测
_MODELS_CACHE: dict[tuple[str, str], list[str]] = {}
_MODELS_LOGGED: set[tuple[str, str]] = set()

# DeepSeek 模型：默认固定用 deepseek-flash（= DeepSeek-V4.1-Flash）。
# 官方当前在售两个：deepseek-flash（Flash 级，本项目默认）、deepseek-v4-pro（Pro 级）。
# 老名字 deepseek-v4-flash 仍可调但模型已下线；deepseek-chat / deepseek-reasoner 已退场。
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"
# 仅在默认模型失效时用于回退，顺序即优先级（全部是 Flash 级，绝不自动升到 Pro）
MODEL_PREFERENCE = ("deepseek-flash", "deepseek-v4-flash")

SYSTEM_PROMPT = (
    "你是一名科技公众号主编，每周为读者做一期 GitHub 开源风向盘点："
    "有信息密度、有观点、不吹不编，读者愿意读完并收藏。"
    "你最在意的是「读者看完能不能真的用上」，而不是把项目说得多么厉害。"
    "只输出 Markdown 正文本身，不要输出任何解释、前言或代码块围栏。"
)

DEFAULT_CANDIDATES = 12   # 候选池大小（榜单名次范围）


# ---------------------------------------------------------------- 工具函数

def log(msg: str) -> None:
    print(msg, flush=True)


def now_cst() -> datetime:
    return datetime.now(CST)


def period_of(since: str, today: datetime | None = None) -> dict:
    """把榜单周期换算成 展示文案 / 文件名 / 起止日期。

    weekly 在周六运行，窗口是"今天往前推 7 天"，即上周六 ~ 本周六，
    正好覆盖 GitHub weekly 榜的统计口径。
    """
    today = today or now_cst()
    days = {"daily": 1, "weekly": 7, "monthly": 30}.get(since, 7)
    start = (today - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    year, week, _ = today.isocalendar()

    if since == "weekly":
        slug = f"{year}-W{week:02d}"
        label = f"{start:%Y-%m-%d} ~ {today:%Y-%m-%d}（{year} 年第 {week} 周）"
        noun = "本周"
    elif since == "monthly":
        slug = f"{today:%Y-%m}"
        start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = f"{start:%Y-%m-%d} ~ {today:%Y-%m-%d}（{today:%Y 年 %m 月}）"
        noun = "本月"
    else:
        slug = f"{today:%Y-%m-%d}"
        label = f"{today:%Y-%m-%d}"
        noun = "今日"

    return {"since": since, "slug": slug, "label": label, "noun": noun, "days": days}


def http_get(url: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_post_json(url: str, payload: dict, timeout: int = HTTP_TIMEOUT) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def gh_headers() -> dict:
    token = os.environ.get("GH_TOKEN", "").strip()
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


# ---------------------------------------------------------------- 1. 抓 Trending

def parse_trending(page: str) -> list[dict]:
    """从 https://github.com/trending 的 HTML 中解析榜单（服务端渲染，直接正则即可）。

    注意星数文案随周期变化：daily = "stars today"，weekly = "stars this week"，
    monthly = "stars this month"。只认 today 的话周榜会全部取到 0。
    """
    name_re = re.compile(r'<h2[^>]*>\s*<a[^>]*href="/([^"]+)"')
    star_re = re.compile(r"([\d,]+)\s*stars (?:today|this week|this month)")
    desc_re = re.compile(r'<p class="col-9[^"]*">\s*(.*?)</p>', re.S)
    lang_re = re.compile(r'itemprop="programmingLanguage">([^<]+)<')

    items = []
    for chunk in page.split('<article class="Box-row">')[1:]:
        m = name_re.search(chunk)
        if not m:
            continue
        full_name = html.unescape(m.group(1)).strip()
        if full_name.count("/") != 1:
            continue
        s = star_re.search(chunk)
        d = desc_re.search(chunk)
        l = lang_re.search(chunk)
        items.append({
            "full_name": full_name,
            "stars_period": int(s.group(1).replace(",", "")) if s else 0,
            "description": html.unescape(re.sub(r"<[^>]+>", "", d.group(1))).strip() if d else "",
            "language": html.unescape(l.group(1)).strip() if l else "",
            "url": f"https://github.com/{full_name}",
        })
    return items


def fetch_trending(since: str = "daily", retries: int = 3) -> list[dict]:
    """首选抓 Trending 页面（真·增速榜）；失败则回退到 Search API 近似。

    页面抓取带重试：GitHub 偶尔慢几秒，单次超时不足以证明它挂了，
    直接降级会让推文质量明显变差（兜底是"新建高星"，不是增速榜）。
    """
    url = f"{TRENDING_URL}?since={since}"
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            page = http_get(url, headers={"Accept": "text/html"}).decode("utf-8", "ignore")
            items = parse_trending(page)
            if items:
                log(f"[1/5] Trending 页面抓取成功，共 {len(items)} 个项目（榜首 {items[0]['full_name']}）")
                return items
            last_err = "页面结构未匹配到条目"
        except Exception as e:  # noqa: BLE001 网络抖动/结构变化都重试
            last_err = str(e)
        if attempt < retries:
            log(f"      ! 第 {attempt} 次抓取失败（{last_err}），{2 ** attempt}s 后重试")
            time.sleep(2 ** attempt)
    log(f"[1/5] Trending 页面抓取失败（{last_err}），改用 Search API 兜底")
    return fetch_trending_via_api(since)


def fetch_trending_via_api(since: str = "daily") -> list[dict]:
    """Search API 近似 Trending：近 N 天新建且星数高的仓库。语义不同，仅作兜底。

    窗口刻意取宽（daily 也用 7 天），因为 1 天窗口内 `created:>` 常常只剩个位数结果，
    兜底要的是"有东西可发"，不是精确复刻增速榜。
    """
    days = {"daily": 7, "weekly": 7, "monthly": 30}.get(since, 7)
    since_date = (now_cst() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"created:>{since_date} stars:>50")
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=25"
    data = json.loads(http_get(url, headers=gh_headers()).decode("utf-8", "ignore"))
    items = [{
        "full_name": r["full_name"],
        "stars_period": 0,
        "description": r.get("description") or "",
        "language": r.get("language") or "",
        "url": r["html_url"],
    } for r in data.get("items", [])]
    if not items:
        raise RuntimeError("Trending 与 Search API 均未取到项目")
    log(f"[1/5] Search API 兜底成功，共 {len(items)} 个项目（榜首 {items[0]['full_name']}）")
    return items


# ---------------------------------------------------------------- 2. 拉项目信息

def fetch_repo_meta(full_name: str) -> dict:
    try:
        j = json.loads(http_get(f"https://api.github.com/repos/{full_name}", headers=gh_headers()).decode())
        return {
            "stars": j.get("stargazers_count", 0),
            "forks": j.get("forks_count", 0),
            "topics": (j.get("topics") or [])[:8],
            "license": ((j.get("license") or {}) or {}).get("spdx_id") or "",
            "homepage": j.get("homepage") or "",
            "created_at": (j.get("created_at") or "")[:10],
        }
    except Exception as e:  # noqa: BLE001 元信息拿不到不影响主流程
        log(f"      ! 元信息获取失败（{e}），使用 Trending 页数据兜底")
        return {}


def fetch_readme(full_name: str) -> str:
    try:
        raw = http_get(
            f"https://api.github.com/repos/{full_name}/readme",
            headers={**gh_headers(), "Accept": "application/vnd.github.raw"},
        ).decode("utf-8", "ignore")
        log(f"      README 拉取成功（{len(raw)} 字符，截断至 {README_MAX_CHARS}）")
        return raw[:README_MAX_CHARS]
    except Exception as e:  # noqa: BLE001
        log(f"      ! README 拉取失败（{e}），模型将仅依据项目元信息写作")
        return ""


def cover_image(full_name: str) -> str:
    return f"https://opengraph.githubassets.com/1/{full_name}"


# ---------------------------------------------------------------- 2.5 选题

SELECT_SYSTEM_PROMPT = (
    "你是一个技术公众号的主编，负责从 GitHub 热榜里挑出「这一期最该写」的那个项目。"
    "你的判断标准很实际：读者能不能看懂、有没有可能真的去用。"
    "只输出一个 JSON 对象，不要输出任何解释、前言或代码块围栏。"
)


def select_candidates(items: list[dict], top_n: int) -> list[dict]:
    """取榜单前 N 名作为候选池（深拷贝，后续补元信息不会污染原列表）。"""
    return [dict(it) for it in items[:max(1, top_n)]]


def build_select_prompt(cands: list[dict], period: dict) -> str:
    noun = period["noun"]
    lines = []
    for i, c in enumerate(cands, 1):
        desc = c.get("description") or "（该项目未填写 description）"
        lines.append(
            f"{i}. {c['full_name']}\n"
            f"   榜单名次：第 {i} 名　|　{noun}新增 Star：{c.get('stars_period') or '—'}　"
            f"|　主语言：{c.get('language') or '未知'}\n"
            f"   官方描述：{desc}"
        )
    return f"""下面这个榜单是 GitHub Trending 的 {noun}热度榜（统计区间 {period['label']}），
按{noun}新增 Star 从高到低排列。请从中挑出**最适合写成一篇公众号推文**的一个项目。

候选列表：
{chr(10).join(lines)}

【选择标准，按重要性排序】
1. **普适性**：大多数人能看懂、也可能用得上。面向普通开发者、上班族、内容创作者的工具优先。
   明确排除：纯学术论文复现、算法竞赛题解、硬件固件、内核驱动、企业级内部脚手架、
   配置模板合集、awesome-xxx 资源清单、纯库/框架底层（读者拿去没法直接用）。
2. **技术新颖度**：这一期读起来要有"新东西"，不要是重复了无数遍的老题材。
3. **偏向工具应用**：最好是有界面或一条命令就能跑起来的工具、能直接落地使用的应用。
   命令行工具、桌面应用、浏览器插件、可自部署服务都算。
4. **热度**：在上述条件差不多时，再按{noun}新增 Star 高低决定。

【重要约束】
- 不要只看第一名。第一名很可能是个热度高但读者用不上的项目（比如只有研究者在意的东西），
  这种情况下**必须往下挑**，这是这道题的意义所在。
- 但也不能为了"接地气"选一个几乎没人关注的项目。热度是基本盘，至少要是榜单里有分量的位置。
- 如果多个候选都合适，选受众更广、更可能被读者真的装起来用的那个。

只输出这个 JSON（不要加任何其他文字，不要加代码块围栏）：
{{"index": <选中项目在候选列表里的序号，整数>, "score": <你给它打的分，0-100 整数>, "reason": "<不超过 60 字的中文理由，说清为什么是它>"}}"""


def pick_candidate(cands: list[dict], period: dict, base: str, api_key: str,
                   model: str, force_top: int | None = None) -> tuple[dict, dict]:
    """让模型从候选里挑一个；任何异常都降级为榜首，绝不中断流水线。

    返回 (选中的项目, 选择元信息)。choice 里 method 字段标明是"模型挑选"还是"降级取榜首"，
    落到文件元信息里，事后能追溯这个选题是怎么来的。
    """
    if force_top is not None:
        idx = max(1, min(force_top, len(cands)))
        log(f"[2/5] --top {force_top}：跳过模型选题，直接取第 {idx} 名")
        return cands[idx - 1], {"method": "forced", "index": idx, "score": None, "reason": ""}

    if len(cands) == 1:
        log("[2/5] 候选只有一个，无需选题")
        return cands[0], {"method": "only-one", "index": 1, "score": None, "reason": ""}

    try:
        payload = build_payload(model, build_select_prompt(cands, period),
                                purpose="选题", system=SELECT_SYSTEM_PROMPT, max_tokens=800)
        code, body = deepseek_request(base, api_key, "/chat/completions", payload)
        if code != 200:
            raise RuntimeError(f"HTTP {code}: {body[:200]}")
        raw = (json.loads(body)["choices"][0]["message"].get("content") or "").strip()
        raw = scrub_markdown(raw)

        # 模型偶尔会多写一句话，这里只把第一个 JSON 对象抠出来
        m = re.search(r"\{.*?\}", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        idx = int(data["index"])
        if not 1 <= idx <= len(cands):
            raise ValueError(f"index {idx} 超出候选范围 1~{len(cands)}")

        chosen = cands[idx - 1]
        meta = {"method": "model", "index": idx,
                "score": data.get("score"), "reason": (data.get("reason") or "").strip()}
        log(f"[2/5] 模型选题：第 {idx} 名 {chosen['full_name']}"
            f"（评分 {meta['score']}）— {meta['reason']}")
        return chosen, meta
    except Exception as e:  # noqa: BLE001 选题失败不能影响出稿
        log(f"[2/5] ! 选题失败（{e}），降级取榜首 {cands[0]['full_name']}")
        return cands[0], {"method": "fallback-top", "index": 1, "score": None, "reason": ""}


# ---------------------------------------------------------------- 3. 生成推文

def build_prompt(repo: dict, readme: str, period: dict, rank: int = 1) -> str:
    noun = period["noun"]
    desc = repo.get("description") or ""
    meta_lines = [
        f"榜单周期：{period['label']}（GitHub Trending {period['since']} 榜，第 {rank} 名）",
        f"仓库：{repo['full_name']}",
        f"地址：{repo['url']}",
        f"语言：{repo.get('language') or '未知'}",
        f"{noun}新增 Star：{repo.get('stars_period') or '—'}",
        f"总 Star：{repo.get('stars', '—')}  Forks：{repo.get('forks', '—')}",
        f"开源协议：{repo.get('license') or '—'}  创建于：{repo.get('created_at') or '—'}",
        # 榜单页没写 description 的仓库很常见（实测周榜首就出现过），要显式告诉模型"确实没有"
        f"官方描述：{desc or '（该项目在 GitHub 上未填写 description，不要自行编造一句话简介）'}",
        f"标签：{', '.join(repo.get('topics') or []) or '—'}",
        f"封面图：{cover_image(repo['full_name'])}",
    ]
    if readme:
        readme_block = (f"README 原文（这是下面所有技术细节的唯一依据；"
                        f"若被截断则以已给出的部分为准，截断处之后的内容不要推测）：\n"
                        f"<readme>\n{readme}\n</readme>")
    else:
        readme_block = ("README：未取到。因此本次只能依据上面的项目元信息写作，"
                        "不要编造任何安装步骤、功能清单或 API 名称；"
                        "相关小节请如实说明「未能获取 README」。")
    return f"""请依据下面的开源项目资料，写一篇**可以直接发布的中文公众号推文**（Markdown 格式，1100~1600 字）。

这是一篇**{noun}开源项目盘点**，主角是 {period['label']} 期间 GitHub 热度最高的项目。
写作视角要站在"{noun} GitHub 都在关注什么"的高度，而不是单纯介绍一个仓库。

━━━ 第一步：先把资料消化透（这一步在心里做，不要写出来）━━━
先通读 README，搞清楚四个问题再动笔：
· 它到底解决什么具体问题？（不是"是一个 XX 工具"，而是"过去你得 A，现在直接 B"）
· 谁最痛？（哪类人、在什么场景下会想装它）
· 它凭什么能做到？（关键技术点或设计取舍，从 README 里找）
· 读完的人下一步该干什么？
想不清楚这四点就说明资料没吃透，宁可写短也不要硬凑。

━━━ 第二步：写成能推出去的推文 ━━━
标题要有钩子、让人想点；开头 2~3 句必须建立"这跟我有关"；
技术点要**翻译成人话**——不要罗列 README 的 feature 列表，而是说清"有了它你能干什么"。

项目资料：
{chr(10).join(meta_lines)}

{readme_block}

━━━ 写作要求 ━━━
1. 结构：一级标题（≤ 24 字，要有钩子，体现"{noun}"的时间感）→ 导语（2~3 句，先讲"{noun}的技术风向"，再落到这个项目）→ "它解决什么问题" → "为什么{noun}突然火了" → "核心亮点"（3~5 条，每条一个加粗小标题，下面一句话讲清"所以呢"）→ "适合谁用"（分 2~3 类具体人群，说清各自的典型场景）→ "快速上手"（最小可运行步骤，含代码块）→ 结尾一句有观点的收尾，引导读者去仓库看看。
2. 全文中文，技术名词、命令、仓库名保留英文原文。
3. **可读性硬要求**：
   - 段落短，一段不超过 4 行，多用小标题切分，方便手机阅读
   - 尽量用"你"来称呼读者，少用"用户""开发者们"这类第三人称
   - 加粗只用来标重点，一段最多一处，不要满屏加粗
   - 禁止营销感叹体：不要"炸裂""吊打""颠覆""神器""史上最强"这类词，
     也不要堆感叹号。推广靠把价值讲清楚，不靠形容词。
4. 提到涨星数据时，必须说明是"{noun}新增"而不是"累计"，两者不要混用。
5. 结尾附一行仓库地址，格式：`仓库：{repo['url']}`

【最重要：必须真实，宁可少写也不能编】
6. 所有事实、数字、功能、命令、API 名称，都必须能在上面的资料里找到出处。
   资料没写的，一律不写——不要"合理推测"，不要补全你没看到的东西。
   注意：允许翻译和重组表达方式，**不允许新增资料里不存在的信息**。
7. 特别容易编造、也是明确禁止的几类：
   - 编造性能数据：提速多少倍、省了多少内存、超越某某产品多少
   - 编造背景故事：融资、团队来历、作者动机、发布时间线
   - 编造使用体验：你没跑过就不要写"实测""亲测""用下来感觉"
   - 编造 API / 函数 / 命令行参数：README 里没有的接口名一个都不能出现
   - 编造对比结论：不要断言它比某个竞品更好，除非资料里明确写了
8. 如果资料不足以撑起某个小节（比如 README 没写安装步骤），就直接写
   "官方 README 未提供安装说明，建议直接看仓库"这类实话，允许小节变短。
   宁可某个部分单薄，也不要靠想象填满。
9. 描述项目亮点时，用"它声称 / README 里写到"这样的措辞区分"项目自己的说法"，
   不要写成你验证过的结论。
10. 不要出现"本文""下面""综上所述"这类套话开头，不要输出任何 Markdown 之外的说明文字。"""


def deepseek_cfg() -> tuple[str, str, str]:
    """返回 (base_url, api_key, model_override)。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    # 官方文档给的就是不带 /v1 的 https://api.deepseek.com，原样用（历史 /v1 也兼容）
    base = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/") or DEFAULT_BASE_URL
    model = os.environ.get("DEEPSEEK_MODEL", "").strip()
    return base, api_key, model


def deepseek_request(base: str, api_key: str, path: str, payload: dict | None = None,
                     timeout: int = LLM_TIMEOUT) -> tuple[int, str]:
    """统一的 DeepSeek 调用出口（GET /models 和 POST /chat/completions 共用）。"""
    req = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": UA,
        },
        method="POST" if payload else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore")


def fetch_available_models(base: str, api_key: str) -> list[str]:
    """GET /models 拿当前可用模型 id。失败返回空列表，由调用方兜底。

    结果按 (base, api_key) 缓存——一次运行里 resolve_model 会被选题和写作各调一次，
    没必要为此打两遍探测请求（既慢又可能触发限流）。
    """
    ck = (base, api_key)
    if ck in _MODELS_CACHE:
        return _MODELS_CACHE[ck]
    try:
        code, body = deepseek_request(base, api_key, "/models", timeout=HTTP_TIMEOUT)
        if code != 200:
            out = []
        else:
            out = [m.get("id", "") for m in (json.loads(body).get("data") or []) if m.get("id")]
    except Exception:  # noqa: BLE001 探测失败不影响主流程
        out = []
    _MODELS_CACHE[ck] = out
    return out


def resolve_model(base: str, api_key: str, override: str) -> str:
    """确定实际要调用的模型名。

    默认锁定 **deepseek-flash（= DeepSeek-V4.1-Flash）**，这是本项目指定的默认模型。
    探测 /models 只用来做两件事：一是确认这个默认名当前仍然有效（无效时报警并回退到
    列表里"档位最接近"的 Flash 级模型，绝不悄悄换成 Pro——Pro 单价是 Flash 的 4.5 倍），
    二是把当前可用列表打出来，方便排查。
    设了 DEEPSEEK_MODEL 则以配置为准，完全跳过探测，且会核实它是否真的可用。
    """
    available = fetch_available_models(base, api_key)
    if available and (base, api_key) not in _MODELS_LOGGED:
        _MODELS_LOGGED.add((base, api_key))
        log(f"      /models 当前可用：{', '.join(available)}")

    if override:
        if available and override not in available:
            log(f"      ! DEEPSEEK_MODEL='{override}' 不在可用列表里，调用大概率会失败，请核对")
        log(f"      模型：{override}（来自 DEEPSEEK_MODEL）")
        return override

    if available and DEFAULT_MODEL not in available:
        log(f"      ! 默认模型 '{DEFAULT_MODEL}' 不在可用列表里，正在回退")
        for cand in MODEL_PREFERENCE:
            if cand in available:
                log(f"      模型：{cand}（回退命中）")
                return cand
        log(f"      ! 没有任何 Flash 级候选可用，保持 {DEFAULT_MODEL} 并交由调用阶段报错")

    log(f"      模型：{DEFAULT_MODEL}（默认，= DeepSeek-V4.1-Flash）")
    return DEFAULT_MODEL


# 本项目开思考模式。理由：
# 1) 选项目这一步需要"横向比较 + 权衡"（热度 / 普适性 / 新颖度 / 能否落地），
#    这是典型需要推理的任务，非思考模式下容易退化成"只看星数取第一名"；
# 2) 写推文时的判断力（哪些能写、哪些资料没支撑不能写）也更稳；
# 3) 代价可接受：一周一次，且周六早 6 点属官方空闲时段，单价减半。
# 副作用要知道：思考模式下 temperature 会被静默忽略（官方行为，传了不报错也不生效），
# 所以开启时不再传 temperature，改用 reasoning_effort 调档。
DEFAULT_THINKING = True


def thinking_enabled() -> bool:
    """是否启用思考模式。DEEPSEEK_THINKING 可覆盖默认值。"""
    raw = os.environ.get("DEEPSEEK_THINKING", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return DEFAULT_THINKING


def build_payload(model: str, prompt: str, purpose: str = "推文生成",
                  system: str | None = None, max_tokens: int | None = None) -> dict:
    """组装请求体。

    DeepSeek 的思考模式默认是开启的（effort 默认 high），这里按任务性质显式决定开或关。
    注意两者互斥的细节：思考模式下 temperature 会被静默忽略（传了不报错但不生效），
    非思考模式下 reasoning_effort 同理。所以按开关分别组装，不要混着传。
    """
    on = thinking_enabled()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system or SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens or 3000,
        "stream": False,
        "thinking": {"type": "enabled" if on else "disabled"},
    }
    if on:
        payload["reasoning_effort"] = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high").strip() or "high"
        log(f"      思考模式：开启（effort={payload['reasoning_effort']}）；"
            f"注意 temperature 将被忽略，{purpose}耗时与费用都会上升")
    else:
        payload["temperature"] = 0.7
        log(f"      思考模式：关闭（{purpose}属资料忠实摘要类任务，无需思维链；temperature=0.7 生效）")
    return payload


def call_llm(prompt: str) -> str:
    base, api_key, override = deepseek_cfg()
    if not api_key:
        raise RuntimeError("缺少 DEEPSEEK_API_KEY")
    model = resolve_model(base, api_key, override)

    payload = build_payload(model, prompt, purpose="推文生成")
    last_err = ""
    for attempt in range(1, LLM_RETRIES + 1):
        code, body = deepseek_request(base, api_key, "/chat/completions", payload)
        if code == 200:
            try:
                j = json.loads(body)
                content = (j["choices"][0]["message"].get("content") or "").strip()
                if not content:
                    raise RuntimeError("模型返回空内容")
                usage = j.get("usage") or {}
                reasoning = (j["choices"][0]["message"].get("reasoning_content") or "")
                log(f"[4/5] {model} 生成成功（{len(content)} 字符"
                    + (f"，含思维链 {len(reasoning)} 字符" if reasoning else "")
                    + f"，tokens in/out = {usage.get('prompt_tokens', '?')}/{usage.get('completion_tokens', '?')}）")
                return scrub_markdown(content)
            except Exception as e:  # noqa: BLE001 响应结构异常也走重试
                last_err = f"响应解析失败：{e}"
        else:
            last_err = f"HTTP {code}: {body[:300]}"
            # 模型名不对是配置问题，重试没意义，直接抛出去让人看见
            if code == 400 and ("model" in body.lower()):
                raise RuntimeError(f"模型名 '{model}' 不被接受，请改 DEEPSEEK_MODEL。{last_err}")
            if code not in (429, 500, 502, 503, 504):
                break
        if attempt < LLM_RETRIES:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"DeepSeek 调用失败：{last_err}")


def extract_title(md: str, fallback: str) -> str:
    """取第一个一级标题作为飞书卡片标题（模型输出必须以此开头）。"""
    for line in md.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    for line in md.splitlines():  # 退而求其次：任何级别的标题
        if line.lstrip().startswith("#"):
            return re.sub(r"^#+\s*", "", line).strip()
    return fallback


def scrub_markdown(text: str) -> str:
    """交付前质检，保证落盘的是干净的**原生 Markdown**。

    做三件事：
    1. 剥掉模型偶尔多包的整段代码块围栏（否则推文里会出现裸 ```markdown）
    2. 把在正文里裸跑的代码块围栏配平（奇数个补一个，避免后面全被吞进代码块）
    3. 去掉行尾空格、统一换行，保证 clone 下来在任何编辑器里格式都不乱
    """
    t = text.strip()

    # 1) 整段被围栏包住 -> 脱掉外层
    m = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", t, re.S)
    if m:
        log("      质检：剥离模型多包的代码块围栏")
        t = m.group(1).strip()

    # 2) 围栏数量为奇数说明有未闭合的围栏，补一个收尾
    if t.count("```") % 2:
        log("      质检：检测到未闭合的代码块围栏，已补全")
        t += "\n```"

    # 3) 清行尾空白 / 连续空行
    t = "\n".join(line.rstrip() for line in t.splitlines())
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    # 4) 标题前后补空行：紧跟在代码块/段落后面的 `## 标题` 在部分渲染器里不会换行
    lines = t.splitlines()
    fixed: list[str] = []
    for line in lines:
        if line.startswith("#") and fixed and fixed[-1].strip():
            fixed.append("")
        fixed.append(line)
    t = "\n".join(fixed)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()

    if not t.startswith("#"):
        log("      质检：开头不是一级标题（不自动改写，交由 prompt 约束）")
    return t


def fallback_article(repo: dict, period: dict, rank: int = 1) -> str:
    """LLM 不可用时的兜底推文。

    注意这里**只输出抓到的原始字段**，不做任何润色或补全——降级路径更要保证真实。
    没抓到 description 的仓库会如实显示"未填写"，而不是编一句话。
    """
    noun = period["noun"]
    desc = repo.get("description") or "（该项目在 GitHub 上未填写 description）"
    return f"""# {noun} GitHub 热度第一：{repo['full_name'].split('/')[-1]}

> 统计区间：{period['label']}　|　榜单名次：第 {rank} 名
> 本文由自动流程生成。**模型调用未成功，以下为 GitHub 原始字段直出，未经任何润色或补充**，
> 因此内容较短；如需完整推文请重跑，或直接看仓库。

## 它是什么

- 仓库：**{repo['full_name']}**
- 官方描述：{desc}

## 原始字段

- 仓库地址：{repo['url']}
- 主语言：{repo.get('language') or '未填写'}
- {noun}新增 Star：{repo.get('stars_period') or '—'}
- 累计 Star：{repo.get('stars', '—')}，Forks：{repo.get('forks', '—')}
- 开源协议：{repo.get('license') or '未填写'}
- 仓库创建于：{repo.get('created_at') or '未获取'}
- 标签：{', '.join(repo.get('topics') or []) or '未填写'}

![cover]({cover_image(repo['full_name'])})
"""


# ---------------------------------------------------------------- 4. 飞书推送

def to_lark_md(md: str, limit: int = FEISHU_MD_LIMIT) -> str:
    """把通用 Markdown 降级成飞书卡片 lark_md 能渲染的语法。

    飞书卡片 markdown 只认：加粗、斜体、删除线、链接、换行、代码块。
    不认标题(#)、表格、行内代码、图片，这里逐条降级，避免消息变成一坨原文。
    """
    text = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)            # 图片 -> 去掉
    text = re.sub(r"^#{1,6}\s*(.+?)\s*$", r"**\1**", text, flags=re.M)  # 标题 -> 加粗
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.M)   # 分割线 -> 去掉

    def _table(m: re.Match) -> str:
        rows = []
        for line in m.group(0).strip().splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue  # 表格分隔行
            rows.append(" · ".join(c for c in cells if c))
        return "\n".join(rows)

    text = re.sub(r"(?:^\|.*\|[ \t]*\n?)+", _table, text, flags=re.M)  # 表格 -> 文本行
    text = re.sub(r"`([^`\n]+)`", r"\1", text)                  # 行内代码 -> 纯文本
    text = re.sub(r"^(\s*)[-*+]\s+", r"\1· ", text, flags=re.M)  # 无序列表 -> 圆点
    text = re.sub(r"^\s*$", "", text, flags=re.M)               # 空行压缩
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + f"\n\n...（正文过长已截断，完整版见仓库 articles/）"
    return text


def feishu_sign(secret: str, timestamp: int) -> str:
    """飞书自定义机器人签名：以 "{ts}\\n{secret}" 为密钥，对空字符串做 HMAC-SHA256。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), b"", digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


# 飞书 webhook 常见错误码 -> 能直接照着做的处置建议
# 码值取自飞书开放平台《自定义机器人使用指南》
FEISHU_ERROR_HINTS = {
    9499: "请求体格式错误或超过 20KB。检查卡片结构 / 调小 FEISHU_MD_LIMIT",
    11232: "被限流（单机器人 100 次/分、5 次/秒），下一次跑就好；别卡在整点发送",
    19001: "webhook 地址无效。FEISHU_WEBHOOK_URL 要形如 "
           "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx（注意 /bot/v2/hook/ 这段不能少）",
    19021: "签名校验失败。机器人在飞书侧开了「签名校验」，需把密钥存成 FEISHU_SIGN_KEY；"
           "也可能是本机与飞书服务器时间偏差超过 1 小时",
    19022: "IP 白名单校验失败。机器人开了「IP 白名单」，但 GitHub Actions 出口 IP 是动态的，"
           "白名单这条路走不通 —— 请在飞书侧改用「签名校验」或「自定义关键词」",
    19024: "自定义关键词未命中。机器人设了关键词，但消息里没出现；"
           "关键词只匹配 text/title 字段，建议直接把关键词写进推文标题",
}


def feishu_error_hint(body: str) -> str:
    """从飞书返回体里挑出错误码，给一行可执行的提示；认不出就返回空串。"""
    try:
        code = int(json.loads(body).get("code", 0))
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    hint = FEISHU_ERROR_HINTS.get(code)
    return f"      → {hint}" if hint else ""


def feishu_send(webhook: str, payload: dict, tag: str = "[5/5]") -> bool:
    """统一出口：加签名 -> POST -> 判成功 -> 失败时给出人话提示。"""
    secret = os.environ.get("FEISHU_SIGN_KEY", "").strip()
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = feishu_sign(secret, ts)

    raw = json.dumps(payload, ensure_ascii=False)
    size = len(raw.encode("utf-8"))
    if size > 20 * 1024:  # 飞书硬限制 20KB，超了直接被拒
        log(f"{tag} ! 报文 {size} 字节已超飞书 20KB 上限，请调小 FEISHU_MD_LIMIT")

    code, resp = http_post_json(webhook, payload)
    try:
        j = json.loads(resp)
    except json.JSONDecodeError:
        j = {}

    if code == 200 and j.get("code", 0) == 0:
        log(f"{tag} 飞书推送成功（报文 {size} 字节）")
        return True

    log(f"{tag} 飞书推送失败 HTTP={code} 报文={size} 字节 resp={resp[:200]}")
    hint = feishu_error_hint(resp)
    if hint:
        log(hint)
    return False


def push_feishu(webhook: str, title: str, md: str, repo: dict, period: dict,
                rank: int = 1, dry_run: bool = False) -> bool:
    body = to_lark_md(md)
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": title[:60]},
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": body}},
                {"tag": "hr"},
                {"tag": "div", "text": {"tag": "lark_md", "content":
                    f"榜单：{period['label']} 第 {rank} 名　|　"
                    f"[{repo['full_name']}]({repo['url']})\n"
                    f"{period['noun']} +{repo.get('stars_period') or 0} ★　|　"
                    f"累计 {repo.get('stars') or '—'} ★　|　生成于 {now_cst():%Y-%m-%d %H:%M}"}},
            ],
        },
    }
    if dry_run:
        raw = json.dumps(card, ensure_ascii=False)
        log(f"[5/5] --dry-run：跳过推送。报文 {len(raw.encode('utf-8'))} 字节，预览如下")
        log("      " + raw[:600] + (" ..." if len(raw) > 600 else ""))
        return True
    return feishu_send(webhook, card)


def ping_feishu(webhook: str) -> bool:
    """配置期连通性自检：只发一条最小文本，不消耗模型额度。"""
    log("[ping] 向飞书发送连通性测试消息 ...")
    ok = feishu_send(webhook, {
        "msg_type": "text",
        "content": {"text": "[Trending Weekly] webhook 连通性测试：收到这条说明 Secret 配好了"},
    }, tag="[ping]")
    if ok:
        log("[ping] 群里应该已经收到测试消息，可以正式跑了")
    return ok


def ping_deepseek() -> bool:
    """DeepSeek 侧自检：列模型 + 用 1 个 token 试打一发，确认模型名和 Key 都对。"""
    base, api_key, override = deepseek_cfg()
    if not api_key:
        log("[ping] ! 未配置 DEEPSEEK_API_KEY，跳过 DeepSeek 自检")
        return False
    log(f"[ping] DeepSeek 自检 base={base}")

    available = fetch_available_models(base, api_key)
    if available:
        log(f"[ping] /models 返回 {len(available)} 个：{', '.join(available)}")
    else:
        log("[ping] ! /models 探测失败（Key 无效或网络不通），继续用默认模型名试打")

    model = resolve_model(base, api_key, override)
    payload = build_payload(model, "回复两个字：收到")
    payload["max_tokens"] = 8  # 自检只花极少量 token
    code, body = deepseek_request(base, api_key, "/chat/completions", payload)
    if code == 200:
        try:
            content = (json.loads(body)["choices"][0]["message"].get("content") or "").strip()
        except Exception:  # noqa: BLE001
            content = "(解析失败)"
        log(f"[ping] DeepSeek 调用成功　模型={model}　返回={content!r}")
        return True
    log(f"[ping] ! DeepSeek 调用失败 HTTP={code} resp={body[:300]}")
    if code == 401:
        log("      → API Key 无效或已过期，检查 DEEPSEEK_API_KEY")
    elif code == 402:
        log("      → 余额不足，去 platform.deepseek.com 充值")
    elif code == 400 and "model" in body.lower():
        log(f"      → 模型名 '{model}' 不被接受，把 DEEPSEEK_MODEL 改成 /models 列出的名字")
    return False


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="GitHub Trending 周榜 -> DeepSeek 推文 -> 飞书")
    ap.add_argument("--dry-run", action="store_true", help="不调 LLM、不推送，只验证抓取与落盘")
    ap.add_argument("--no-push", action="store_true", help="生成但不推送飞书")
    ap.add_argument("--top", type=int, default=0,
                    help="强制指定取榜单第几名（1 起）。不传则让模型从候选里挑选，默认自动")
    ap.add_argument("--candidates", type=int, default=DEFAULT_CANDIDATES,
                    help=f"候选池大小，默认 {DEFAULT_CANDIDATES}（仅在自动选题时生效）")
    ap.add_argument("--since", default="weekly", choices=["daily", "weekly", "monthly"],
                    help="榜单周期，默认 weekly（GitHub 近一周热度榜）")
    ap.add_argument("--ping", action="store_true",
                    help="自检：验飞书 webhook + DeepSeek 模型/Key 连通性，不抓榜单")
    args = ap.parse_args()

    today = now_cst()

    # 配置期自检：配完 Secret 先 ping 一下，比跑一遍全流程省事得多
    if args.ping:
        log("=== 自检模式（不抓榜单、不写文件、不推送正文）===")
        webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
        if not webhook:
            log("[ping] ! 未配置 FEISHU_WEBHOOK_URL，跳过飞书自检")
        feishu_ok = ping_feishu(webhook) if webhook else True
        ds_ok = ping_deepseek()
        log(f"=== 自检结果：飞书 {'OK' if feishu_ok else 'FAIL'}　"
            f"DeepSeek {'OK' if ds_ok else 'FAIL'} ===")
        return 0 if (feishu_ok and ds_ok) else 1

    period = period_of(args.since, today)
    log(f"=== GitHub Trending 推文流水线 {today:%Y-%m-%d %H:%M:%S} (+08) ===")
    log(f"    榜单周期：{period['since']}　统计区间：{period['label']}")

    # 1. 榜单
    items = fetch_trending(args.since)

    # 2. 选题：不再无脑取第一名，而是让模型在候选池里挑"读者用得上"的那个
    base, api_key, override = deepseek_cfg()
    model_used = "（dry-run 未调用）" if args.dry_run else resolve_model(base, api_key, override)

    if args.dry_run:
        cands = select_candidates(items, args.candidates)
        choice = {"method": "dry-run", "index": 1, "score": None, "reason": ""}
        repo = dict(cands[0])
        log(f"[2/5] --dry-run：跳过选题，取第 1 名 {repo['full_name']}")
    else:
        cands = select_candidates(items, args.candidates)
        repo, choice = pick_candidate(cands, period, base, api_key, model_used,
                                      force_top=args.top or None)

    rank = choice["index"]
    log(f"      本期项目：{repo['full_name']}（榜单第 {rank} 名，"
        f"{period['noun']} +{repo.get('stars_period') or 0} ★）")

    # 3. 项目信息
    log(f"[3/5] 补全 {repo['full_name']} 的元信息与 README ...")
    repo.update(fetch_repo_meta(repo["full_name"]))
    readme = fetch_readme(repo["full_name"])

    # 4. 生成正文
    if args.dry_run:
        log("[4/5] --dry-run：跳过模型调用，使用兜底模板")
        article = fallback_article(repo, period, rank)
    else:
        try:
            article = call_llm(build_prompt(repo, readme, period, rank))
        except Exception as e:  # noqa: BLE001 模型挂了不能中断流水线
            log(f"[4/5] ! 生成失败：{e}；降级为模板推文")
            article = fallback_article(repo, period, rank)

    # 交付前统一质检：保证落盘的是干净的原生 Markdown（标题必须是全文第一个元素）
    article = scrub_markdown(article)
    title = extract_title(article, repo["full_name"])

    # 头部元信息以 HTML 注释形式放在最前——这是**合法的原生 Markdown**，
    # 任何 Markdown 编辑器/渲染器都会忽略它，公众号编辑器粘贴时也不会带进去；
    # 但 git 历史里留下了"哪个模型、哪个榜单、哪个项目、怎么选出来的"完整出处。
    pick_desc = {
        "model": f"模型从 {len(cands)} 个候选里选中（评分 {choice.get('score')}）",
        "forced": "人工指定 --top",
        "only-one": "候选只有一个",
        "fallback-top": "选题失败，降级取榜首",
        "dry-run": "dry-run 未选题，取榜首",
    }.get(choice["method"], choice["method"])
    doc = (f"<!-- generated by Trending/trending_article.py at {today:%Y-%m-%d %H:%M:%S} +08:00 -->\n"
           f"<!-- trending: {args.since} | period {period['label']} | rank #{rank} | "
           f"{period['noun']} +{repo.get('stars_period') or 0} stars -->\n"
           f"<!-- model: {model_used} | thinking: {'on' if thinking_enabled() else 'off'} -->\n"
           f"<!-- selected: {pick_desc}"
           + (f" | {choice['reason']}" if choice.get("reason") else "") + " -->\n"
           f"<!-- source: {repo['url']} -->\n\n"
           f"{article}\n")

    OUT_DIR.mkdir(exist_ok=True)
    out_file = OUT_DIR / f"{period['slug']}.md"
    out_file.write_text(doc, encoding="utf-8")
    LATEST.write_text(doc, encoding="utf-8")
    log(f"      已写入 {out_file.relative_to(ROOT)} 与 {LATEST.name}"
        f"（正文 {len(article)} 字符，原生 Markdown）")

    # 5. 推送
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if args.no_push or not webhook:
        log("[5/5] 未配置 FEISHU_WEBHOOK_URL 或指定 --no-push，跳过推送")
        return 0
    push_feishu(webhook, title, article, repo, period, rank, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        log(f"FATAL: {exc}")
        sys.exit(1)
