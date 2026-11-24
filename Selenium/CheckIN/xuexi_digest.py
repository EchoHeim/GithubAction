# -*- coding: UTF-8 -*-
"""学习强国「10 条短讯」—— 取正文、压到 30 字以内、推给你。

━━━ 为什么不用浏览器 ━━━
正文在 `https://boot-source.xuexi.cn/data/app/<itemId>.js` 里就是现成的 JSONP：
`title` / `content` / `normalized_content` / `publish_time` 全都有，一个 GET 就拿到。
用浏览器打开再「完整读完」，多出来的唯一效果是让平台记一条阅读记录 —— 那是另一件事。
所以这里没有 Selenium、没有停留、没有循环等待：**纯 HTTP + 文本处理**。

━━━ 摘要怎么来的 ━━━
两层，按有没有配 LLM 决定：

1. 配了 `LLM_API_KEY`（OpenAI 兼容接口）→ 真摘要，按 30 字压缩。
   `LLM_BASE_URL` 默认 https://api.openai.com/v1，`LLM_MODEL` 默认 gpt-4o-mini。
2. 没配 → **机械压缩**：时政新闻的标题本身就是结论（实测 10 条里 7 条标题 ≤30 字），
   标题放得下就直接用；放不下就剥掉书名号里的书名/文号再截断，末尾加「…」。
   这条路径不需要任何外部服务，跑在 CI 里也不会因为模型超时而失败。

⚠️ 机械压缩**不是总结**，它只是把标题剪到 30 字。要真摘要就配 key，
   两者质量差得很明显，脚本会把当前用的是哪条路径打在日志第一行。

━━━ 用法 ━━━
    python -B Selenium/CheckIN/xuexi_digest.py            # 10 条，近 3 天（不够自动放宽）
    python -B Selenium/CheckIN/xuexi_digest.py 6 7        # 6 条，近 7 天
    FEISHU_BOT_ID=https://... python -B Selenium/CheckIN/xuexi_digest.py   # 顺带推卡片

退出码：正常 0；列表或正文全取不到 1。
"""

import html
import json
import os
import re
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Selenium.CheckIN.xuexi_reading_list import pick_with_widen, fetch_items, ARTICLE_LIST  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DETAIL_URL = "https://boot-source.xuexi.cn/data/app/%s.js"
LIMIT = 30


def http_text(url, timeout=25):
    """取一段文本。站点不发 charset，不显式指定就会解成 latin-1 乱码。"""
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def fetch_detail(item_id):
    """取一篇的正文。接口是 JSONP（`callback({...})`），剥壳后按 JSON 解。"""
    raw = http_text(DETAIL_URL % item_id)
    start, end = raw.find("("), raw.rfind(")")
    if start < 0 or end <= start:
        raise RuntimeError("不是 JSONP：%s" % raw[:60])
    return json.loads(raw[start + 1 : end])


def plain_text(content_html):
    """HTML 正文 → 纯文本。只去标签和常见实体，够喂摘要就行，不上解析器。"""
    text = re.sub(r"<script.*?</script>", "", content_html or "", flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def squeeze(title, text, limit=LIMIT):
    """兜底压缩：先把「书名号里的书名/文号」剥掉，再按字数截断。

    时政标题本身就接近短讯（实测 10 条有 7 条 ≤30 字），所以优先原样用；
    超长时剥书名号 —— `习近平《在纪念孙中山先生诞辰160周年大会上的讲话》单行本出版`
    剥成 `习近平 单行本出版` 那种残句，所以剥完太短就退回不剥的版本。
    """
    title = (title or "").strip()
    if len(title) <= limit:
        return title

    stripped = re.sub(r"《[^》]*》", "", title).strip()
    stripped = re.sub(r"\s{2,}", " ", stripped)
    # 剥完剩不下东西、或者只剩个别字，说明书名号里就是主体，退回原题
    if len(stripped) >= 10 and len(stripped) < len(title):
        if len(stripped) <= limit:
            return stripped

    # 还放不下就截断，末尾留一个省略号（占 1 字）
    return title[: limit - 1] + "…"


def llm_summary(title, text, api_key, base_url, model, limit=LIMIT):
    """真摘要（OpenAI 兼容接口）。失败返回 None，由调用方退回机械压缩。"""
    prompt = (
        "把下面这条新闻压缩成一句中文短讯，不超过 %d 个字，"
        "只保留最关键的人、事、结果，不要评论，不要引号，直接输出短讯本身。\n\n"
        "标题：%s\n正文：%s" % (limit, title, text[:1200])
    )
    try:
        resp = requests.post(
            base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 80,
            },
            timeout=40,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = content.replace("\n", " ").strip('"“”')
        return content[:limit] if content else None
    except Exception as err:
        print("[WARN] LLM 摘要失败，退回机械压缩: %s" % str(err)[:80])
        return None


def build(count, days):
    items, window = pick_with_widen(fetch_items(ARTICLE_LIST), count, days)
    print("===> 选稿: %d 篇（窗口 %d 天）" % (len(items), window))

    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    mode = "LLM 摘要（%s）" % model if api_key else "机械压缩（标题剪到 30 字，不是总结）"
    print("===> 摘要方式: %s" % mode)

    rows = []
    for idx, item in enumerate(items, 1):
        item_id = item["id"]
        title, text, source, published = item["title"], "", "", item["when"]
        try:
            detail = fetch_detail(item_id)
            title = detail.get("title") or title
            text = detail.get("normalized_content") or plain_text(detail.get("content"))
            source = detail.get("orig_source") or detail.get("show_source") or ""
            published = (detail.get("publish_time") or item["when"])[:16]
        except Exception as err:
            print("[WARN] 第 %d 篇正文取不到（用标题兜底）: %s" % (idx, str(err)[:70]))

        brief = llm_summary(title, text, api_key, base_url, model) if api_key else None
        if not brief:
            brief = squeeze(title, text)

        rows.append(
            {
                "brief": brief,
                "title": title,
                "source": source or item["channel"],
                "when": published,
                "url": item["url"],
            }
        )
        print("%2d. %s" % (idx, brief))
        # 礼貌间隔：10 次 GET 不值得打太快，也省得触发限流
        time.sleep(0.3)
    return rows


def to_card(rows):
    lines = ["**今日 %d 条**" % len(rows), ""]
    for idx, row in enumerate(rows, 1):
        lines.append("%d. %s" % (idx, row["brief"]))
        lines.append("    %s · [原文](%s)" % (row["source"], row["url"]))
    return "\n".join(lines)


def _int_arg(argv, index, default):
    try:
        value = int(str(argv[index]).strip())
    except (IndexError, ValueError):
        return default
    return value if value > 0 else default


def main():
    count = _int_arg(sys.argv, 1, 10)
    days = _int_arg(sys.argv, 2, 3)

    try:
        rows = build(count, days)
    except Exception as err:
        print("[X] 取稿失败: %s" % str(err)[:120])
        return 1
    if not rows:
        print("[X] 没取到条目")
        return 1

    print("\n===> 最长一条 %d 字（上限 %d）" % (max(len(r["brief"]) for r in rows), LIMIT))
    over = [r["brief"] for r in rows if len(r["brief"]) > LIMIT]
    if over:
        print("[WARN] 有 %d 条超限: %r" % (len(over), over))

    bot_id = os.getenv("FEISHU_BOT_ID") or ""
    if bot_id:
        from Messaging.Feishu import Feishu_SendCardMsg

        Feishu_SendCardMsg(bot_id, " 学习强国 · 今日短讯 ", to_card(rows))
    else:
        print("\n（没给 FEISHU_BOT_ID，只打印不推送）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
