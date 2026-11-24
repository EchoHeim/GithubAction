# -*- coding: UTF-8 -*-
"""学习强国（qiangguo）每日签到：Cookie 复用登录态 + 积分快照。

━━━ 为什么只能走 Cookie ━━━
pc.xuexi.cn 的登录入口**只有扫码**：login.html 的 bundle 里只有 qrcode，
文案写死「用学习强国扫码登录，如未安装扫码下载」——没有账号密码、
没有短信、没有第三方授权。

但登录态本身完全挂在 cookie 上，用的是 `token`（domain=`.xuexi.cn`）。
前端只做**存在性判断**，压根不校验：

    if (!o.a.get("token")) return b(), !0;      // b() 跳 /points/login.html?ref=...

真正的校验在后端。拿一个假 token 打积分接口，服务端原话：

    GET https://pc-proxy-api.xuexi.cn/delegate/score/today/query
    Cookie: token=deadbeef
    → {"data":null,"message":"token check failed","code":401,"ok":false}

也就是说：**只要 token 有效，注入 cookie 就等于登录**，
不需要设备指纹，也没有「扫码会话」绑定。

━━━ 「签到」在这里到底是什么 ━━━
学习强国没有独立的「签到」按钮，积分是**行为积分**（每日登录 1 分、
阅读文章 1 分/篇、活跃时段翻倍……见 `/delegate/score/scoreDescription`）。

所以本脚本只做两件能如实汇报的事：
  1. 用 cookie 打开一次积分页，让站点自己跑完整前端 —— 登录态判断、埋点上报
     都真的走一遍。这一步才是「登录」，不是 curl 一下接口就算数；
  2. 用同一个 token 打积分接口，把**今日积分 / 累计积分 / 各项任务进度**记下来。
     顺带看「登录」那一项满没满分 —— 满了说明今天的登录分已到账，就不用再开页面了。

⚠️ **不刷分**：脚本不模拟阅读/观看/答题。今日积分没涨就照实写「未变化」，
   别把它包装成「签到成功」——学习强国按行为计分，读一次接口本身不产生积分。
   想要分数就自己去读文章，这不是脚本能替你做的部分。

用法：
    XUEXI_COOKIE="token=xxxx; __UID__=yyyy" python -m Selenium.CheckIN.xuexi

可选环境变量：
    XUEXI_COOKIE    登录态 Cookie，`token=...; __UID__=...` 整行，
                    或**只贴 token 的值**（脚本自动补 token=），唯一必需项
    FEISHU_BOT_ID   飞书机器人 webhook，给了才推卡片
    XUEXI_BROWSER   置 1 才开浏览器（默认 0）：开一次积分页，让站点跑完整前端。
                    CI 里由 workflow 显式置 1；本机默认不开 —— 本机取 chromedriver
                    常被安全策略杀进程，见 LOCAL_RUN.md。

退出码：0 正常（含「积分未变化」）；非 0 = cookie 失效 / 接口异常 / 没凭据。
"""

import json
import os
import re
import sys
import time

from Selenium.base import *
from Messaging.Feishu import Feishu_SendCardMsg

POINTS_URL = "https://pc.xuexi.cn/points/my-points.html"
# 登录页只作诊断用：Cookie 不被接受时前端会跳到这里（带 ?ref= 回跳参数）
LOGIN_URL_MARKER = "login.html"

# 积分接口都挂在 pc-proxy-api 上（前端 bundle 里 examApiHost 就是这个域名）。
# ⚠️ 别换成 pc-api.xuexi.cn —— 那是 /open/api/auth/check、getGray 用的，
#    积分接口在它上面一律返回 404「接口不存在」。
API_HOST = "https://pc-proxy-api.xuexi.cn"
TODAY_PATH = "/delegate/score/today/query"
DAYS_PATH = "/delegate/score/days/listScoreProgress"
DETAIL_PATH = "/delegate/score/detail/query"

COOKIE_DOMAIN = ".xuexi.cn"
COOKIE_ENV = "XUEXI_COOKIE"

DEBUG_DIR = os.path.join(os.getcwd(), "xuexi-debug")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 只贴 token 值时，靠这个前缀判断用户贴的是整行还是裸值
_COOKIE_HEADER_RE = re.compile(r"^\s*(token|__UID__|tmzw)\s*=")


def normalize_cookie(raw):
    """把用户贴进来的东西规整成可用的 Cookie 行。

    三种情况：
      - `token=xxx; __UID__=yyy` → 原样用；
      - `abc123...`（只贴了 token 的值）→ 补成 `token=abc123...`；
      - 空 → 空（调用方负责报错）。

    ⚠️ 不能简单用「含不含 =」判断：token 值本身可能带 base64 的补位 `=`。
    所以只认**名字是不是 token/__UID__/tmzw**，盲贴也不会把值当成名字。
    """
    raw = (raw or "").strip().strip(";").strip()
    if not raw:
        return ""
    if ";" in raw or _COOKIE_HEADER_RE.match(raw):
        return raw
    return "token=" + raw


def make_session(cookie_header):
    """建一个带 cookie 的 requests 会话。

    cookie 直接塞请求头，不走 cookiejar —— jar 对 `domain=.xuexi.cn` 的匹配
    规则比浏览器挑剔，跨子域请求容易悄悄丢 cookie，症状是「明明给了 token 却 401」。
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Referer": POINTS_URL,
            "Origin": "https://pc.xuexi.cn",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_header,
        }
    )
    return session


def _dump(name, data):
    """把原始响应落盘。接口结构一旦变了，靠它自证，不用猜。"""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, "%s_%s.json" % (name, time.strftime("%H%M%S")))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        return path
    except (OSError, TypeError, ValueError) as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (name, err))
        return ""


def call_api(session, path, method="GET", params=None, payload=None, label=""):
    """打一个积分接口，返回 `data` 字段。

    token 失效在这里就地定性 —— 401 + "token check failed" 是服务端原话，
    不要跟网络错误混在一起（两者让用户做的事完全不同：一个去重扫，一个重试）。
    """
    url = API_HOST + path
    try:
        if method == "POST":
            resp = session.post(url, json=payload or {}, timeout=20)
        else:
            resp = session.get(url, params=params or {}, timeout=20)
    except requests.RequestException as err:
        raise RuntimeError("%s 请求失败（网络问题，不是凭据问题）: %s" % (label, err))

    try:
        body = resp.json()
    except ValueError:
        _dump("bad_json_%s" % label, {"status": resp.status_code, "text": resp.text[:2000]})
        raise RuntimeError(
            "%s 返回的不是 JSON（HTTP %s），可能是 IP 被风控或接口下线" % (label, resp.status_code)
        )

    code = body.get("code")
    if code == 401 or "token check failed" in str(body.get("message", "")):
        raise RuntimeError(
            "Cookie 里的 token 已失效（服务端：%s）。\n"
            "    重新取一份：浏览器登录 %s → F12 → Application → Cookies → pc.xuexi.cn\n"
            "    → 复制 token → 更新 GitHub Secret %s"
            % (body.get("message"), POINTS_URL, COOKIE_ENV)
        )
    if not body.get("ok"):
        _dump("api_error_%s" % (label or path.strip("/").replace("/", "_")), body)
        raise RuntimeError(
            "%s 返回异常：code=%s message=%s" % (label, code, body.get("message"))
        )
    return body.get("data")


def _as_number(value):
    """接口把 5 分写成 5.0 —— 卡片上要的是 5，整数值别拖个小数点。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else number


def read_today_score(session):
    """今日积分 → `data.score`。

    实测响应（2026-11-24）：
        {"data":{"userId":151170734596,"score":5.0,"scoreV2":"0",...}}
    """
    data = call_api(session, TODAY_PATH, label="今日积分")
    if isinstance(data, dict) and "score" in data:
        return _as_number(data["score"])
    _dump("today_unknown", data)
    print("[WARN] 今日积分结构变了，原始响应已落盘 xuexi-debug/")
    return None


def read_progress(session):
    """今日任务进度 + 账号健康状态。

    ⚠️ **deviceType=1（App 侧）才拿到全部 9 项**。deviceType=2（PC 侧）只回 4 项：
    登录 / 我要选读文章 / 我要视听学习 / 每日答题，而订阅、发表观点、本地频道、
    趣味答题、强国运动这 5 项 PC 端根本不列 —— 照着 PC 那份算「今天还差多少分」
    会漏掉 14 分。所以这里固定用 1。

    实测响应（2026-11-24）：

        {"userId":151170734596,"inBlackList":false,"needFaceRecognition":false,
         "totalScore":5,
         "taskProgress":[{"title":"我要选读文章","currentScore":1,"dayMaxScore":12,
                          "periodType":1,...}, ...]}

    ⚠️ 这里的 `totalScore` 是**今天**各项之和，不是累计总积分 ——
    累计总分得靠 read_total_score() 从明细里推，两个别混。

    ⚠️ 参数名是 `sence`（站点自己的拼写错误），照抄，改成 sense 会查不到。
    """
    data = call_api(
        session, DAYS_PATH, params={"sence": "score", "deviceType": 1}, label="今日进度"
    )
    if not isinstance(data, dict):
        _dump("progress_unknown", data)
        raise RuntimeError("今日进度结构变了（返回的不是对象），原始响应已落盘 xuexi-debug/")

    tasks = []
    for row in data.get("taskProgress") or []:
        if not isinstance(row, dict):
            continue
        # periodType=1 是「每日」，2 是「每周」（实测只有强国运动是 2）。
        # 每周项也要显示 —— 但**不让它参与「今天还差多少」的计算**，
        # 否则一周里剩下的六天都会把已领完的 2 分算成缺口。
        tasks.append(
            {
                "title": row.get("title") or "?",
                "score": _as_number(row.get("currentScore") or 0),
                "max": _as_number(row.get("dayMaxScore") or 0),
                "daily": row.get("periodType") in (None, 1),
            }
        )

    return {
        "total": _as_number(data.get("totalScore") or 0),
        "tasks": tasks,
        "in_blacklist": bool(data.get("inBlackList")),
        "need_face": bool(data.get("needFaceRecognition")),
    }


def read_total_score(session):
    """累计总积分。

    ⚠️ 没有「总分」接口，只能从**积分明细**里推：`detail/query` 每条记录的
    `currentScore` 是「这笔入账**之后**的累计值」，按时间倒序 ——
    所以第 1 条就是当前总分。实测三条：752（视听学习 +1）← 751（阅读文章 +1）
    ← 750（强国运动 +2），倒推顺序对得上。

    一条记录都没有时返回 None，卡片写「未读取到」—— 不要填 0 骗自己。
    """
    data = call_api(
        session,
        DETAIL_PATH,
        method="POST",
        payload={"pageNo": 1, "pageSize": 1},
        label="积分明细",
    )
    rows = (data or {}).get("list") or []
    if not rows:
        return None
    return _as_number(rows[0].get("currentScore"))


def visit_points_page(cookie_header):
    """注入 cookie 后真开一次积分页 —— 这才是「登录」，接口校验只是核对结果。

    返回 (是否成功, 落地 URL, 备注)。失败只记日志、不抛异常：
    浏览器这步的意义是「真实会话」，它挂了不影响用接口把积分读出来。
    """
    driver = None
    try:
        driver = get_web_driver()
        inject_cookies(driver, cookie_header, COOKIE_DOMAIN)
        driver.get(POINTS_URL)

        # page_load_strategy="none"：get() 立即返回，此刻 DOM 可能还是 about:blank。
        # 等 URL 真落到 xuexi.cn 再判断，别用固定 sleep 冒充「加载完成」。
        if not wait_url(driver, "xuexi.cn", 40):
            return False, "?", "页面 40s 内没落地（CDN 或网络问题）"

        # 前端拿到 token 后会去打 auth/check + 积分接口，给它点时间跑完埋点
        time.sleep(3)
        url = driver.current_url or ""

        # 直接确认 cookie 到底进没进去（token 非 HttpOnly，页面里读得到）
        try:
            has_token = driver.execute_script(
                "return document.cookie.indexOf('token=') >= 0"
            )
        except WebDriverException:
            has_token = None
        if has_token is False:
            return False, url, "页面里读不到 token cookie，注入没生效"

        if LOGIN_URL_MARKER in url:
            return False, url, "前端把页面踢回登录页（token 不被接受）"

        return True, url, ""
    except WebDriverException as err:
        # 本机常见原因：Selenium Manager 联网取 chromedriver 被安全策略杀掉，
        # 现象是进程直接 SIGTERM、一行日志都没有（见 LOCAL_RUN.md）。
        return False, "", (
            "浏览器步骤失败: %s（这就是脚本默认不开浏览器的原因；CI 的 "
            "chromedriver 是 setup-chromedriver 装好的，不受影响）" % str(err)[:100]
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception as err:
                print("[WARN] 关闭浏览器失败: %s" % err)


def notify(bot_id, status, today="", total="", progress="", gap="", account="", note=""):
    """推飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append(
        "**今日积分**: %s" % ("%s 分" % today if today not in ("", None) else "未读取到")
    )
    content.append(
        "**累计积分**: %s" % ("%s 分" % total if total not in ("", None) else "未读取到")
    )
    if progress:
        content.append("**今日进度**: %s" % progress)
    if gap:
        content.append("**今日缺口**: %s" % gap)
    if account:
        content.append("**账号状态**: %s" % account)
    if note:
        content.append("**备注**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        Feishu_SendCardMsg(bot_id, " 学习强国 签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """凭据只走环境变量：Cookie 动辄几百字符，命令行参数容易被截断/转义吃掉。"""
    return {
        "cookie": normalize_cookie(os.getenv(COOKIE_ENV)),
        "bot_id": os.getenv("FEISHU_BOT_ID") or (argv[1] if len(argv) > 1 else ""),
    }


def qiangguo(cookie="", bot_id=""):
    print("===> 凭据检查: cookie=%d字 / FEISHU_BOT_ID=%d字" % (len(cookie or ""), len(bot_id or "")))
    if not cookie:
        sys.exit(
            "[X] 没有 Cookie。学习强国只能扫码登录，但登录态可以复用。\n"
            "    取法：浏览器扫码登录 %s\n"
            "          F12 → Application → Storage → Cookies → https://pc.xuexi.cn\n"
            "          复制 token 的 Value（整行 Cookie 也行），填进环境变量 %s"
            % (POINTS_URL, COOKIE_ENV)
        )

    pairs = parse_cookie_header(cookie)
    # 名字不是机密（站点 cookie 名固定），值绝不打印
    print("===> Cookie 项(%d): %s" % (len(pairs), ", ".join(name for name, _ in pairs)))
    if not any(name == "token" for name, _ in pairs):
        sys.exit(
            "[X] Cookie 里没有 token —— 学习强国认的就是它。\n"
            "    你给的是: %s" % ", ".join(name for name, _ in pairs)
        )

    session = make_session(cookie)
    status = "签到失败"
    note = ""
    today = total = progress = gap = account = ""

    try:
        # 先用接口验一次：token 失效就在 10 秒内说清楚，不用白等浏览器起停
        today = read_today_score(session)
        print("===> Token 有效，今日积分: %s" % today)

        # 进度/总分是卡片的血肉，但读不到不该拖垮签到本身（同 52pojie 读吾爱币的原则）
        prog = {"tasks": [], "in_blacklist": False, "need_face": False}
        prog_ok = False
        try:
            prog = read_progress(session)
            prog_ok = True
            progress = " ｜ ".join(
                "%s %s/%s%s"
                % (t["title"], t["score"], t["max"], "" if t["daily"] else "（周）")
                for t in prog["tasks"]
            )
            print("===> 今日进度: %s" % (progress or "未读取到"))
        except Exception as err:
            print("[WARN] 今日进度读取失败（不影响结论）: %s" % err)

        try:
            total = read_total_score(session)
            print("===> 累计积分: %s" % total)
        except Exception as err:
            print("[WARN] 累计积分读取失败（不影响结论）: %s" % err)

        # 今天还差多少 —— 「想拿满分该补哪几项」的入口，进度行已经写明差在哪
        gap = ""
        daily = [t for t in prog["tasks"] if t["daily"]]
        if daily:
            sum_max = sum(t["max"] for t in daily if isinstance(t["max"], (int, float)))
            sum_now = sum(t["score"] for t in daily if isinstance(t["score"], (int, float)))
            gap = "还差 %s 分（%s/%s，只算每日项）" % (sum_max - sum_now, sum_now, sum_max)
            print("===> 今日缺口: %s" % gap)

        # 账号健康：真被风控了，上面所有数字都不可信，得先说出来
        account = "正常"
        if prog.get("in_blacklist"):
            account = "⚠️ 在平台黑名单里"
        elif prog.get("need_face"):
            account = "⚠️ 需要人脸核验"
        if account != "正常":
            print("[WARN] 账号状态: %s" % account)

        # 「登录」任务满分 = 今天的登录分已经到账。这时再开浏览器纯属浪费 30 秒，
        # 所以把「要不要开页面」交给这个信号决定，而不是每次都跑。
        login_task = next((t for t in prog["tasks"] if "登录" in t["title"]), None)
        login_done = bool(login_task and login_task["score"] and login_task["score"] >= 1)

        if not prog_ok:
            # 进度接口挂了就**不能**说「登录分未到账」—— 那是把「读不到」当成「没拿到」，
            # 卡片会变成假消息。这种情况只报「读不到」，让人去看日志。
            status = "仅接口校验（进度读取失败）"
            note = "今日进度接口没读成功，无法判断登录分是否到账"
            print("[WARN] %s" % note)
        elif login_done:
            status = "今日登录分已到账"
            print(
                "===> 「登录」任务 %s/%s，今天的登录分已经拿到，不再开页面"
                % (login_task["score"], login_task["max"])
            )
        elif os.getenv("XUEXI_BROWSER") == "1":
            # 只有「登录分还没到账」时才值得开浏览器。
            # ⚠️ 默认不开的原因很实际：本机 Selenium Manager 取 chromedriver 会被安全策略
            #    直接杀进程（SIGTERM，一行日志都没有），那种死法 try/except 都兜不住。
            #    CI 的 chromedriver 由 setup-chromedriver 装好，workflow 显式置 1。
            print("===> 「登录」任务未完成，打开积分页建立页面会话")
            ok, url, why = visit_points_page(cookie)
            if ok:
                print("===> 页面落地: %s" % url)
                # 页面跑完立刻回查登录分有没有从 0 跳到 1 —— 这是唯一能自证的判据，
                # 别拿「页面打开了」冒充「登录分拿到了」。
                time.sleep(2)
                try:
                    after = read_progress(session)
                except Exception as err:
                    print("[WARN] 回查进度失败: %s" % err)
                    after = {"tasks": []}
                hit = next((t for t in after["tasks"] if "登录" in t["title"]), None)
                got_it = bool(hit and hit["score"] and hit["score"] >= 1)
                status = "登录分已到账（页面会话触发）" if got_it else "会话已建立，登录分未到账"
                note = "页面会话已建立；登录分%s" % ("已到账" if got_it else "仍未到账")
                try:
                    refreshed = read_today_score(session)
                    if refreshed is not None:
                        today = refreshed
                except Exception as err:
                    print("[WARN] 回查今日积分失败: %s" % err)
            else:
                status = "仅接口校验（浏览器未成功）"
                note = why
                print("[WARN] %s" % why)
        else:
            status = "登录分未到账（未开浏览器）"
            note = "XUEXI_BROWSER 未置 1，只验证 token + 读积分；置 1 会真开一次积分页"
            print("===> 「登录」任务未完成，但 XUEXI_BROWSER 未置 1，跳过浏览器")

        print("===> 签到结果: %s" % status)
    except Exception as err:
        status = "签到失败"
        note = str(err)[:200]
        raise
    finally:
        if bot_id:
            notify(bot_id, status, today, total, progress, gap, account, note)


if __name__ == "__main__":
    if len(sys.argv) == 1 and not os.getenv(COOKIE_ENV):
        sys.exit(
            "用法: python -m Selenium.CheckIN.xuexi\n"
            "  凭据只走环境变量 %s（取法见 LOCAL_RUN.md）\n"
            "  可选: python -m ... <飞书机器人 webhook>"
            % COOKIE_ENV
        )
    qiangguo(**resolve_credentials(sys.argv))
