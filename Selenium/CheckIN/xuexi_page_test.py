# -*- coding: UTF-8 -*-
"""学习强国 PC 端页面冒烟测试 —— 只回答一个问题：这些页面**打不打得开**。

━━━ 这个脚本刻意不做的事 ━━━
**不模拟停留。** 打开 → 读状态码/耗时/标题 → 断开，一次过，不 sleep、不重试、不循环。
原因是「阅读积分」来自停留时长与页面自己的上报；一旦挂上 60 秒停留，这个脚本就从
「可达性测试」变成「制造阅读记录」。这两件事的界线就在这里，代码里也钉着注释。

所以它跑一百遍也不会给你多一分，测的是**网络与站点可用性**：

  - 页面能不能打开（状态码、耗时、字节数）
  - 拿到的是不是真内容（`<title>`、是否被 404/登录页/WAF 顶替）
  - 同一批 URL 在**本机**和 **CI runner（海外 IP）** 上差多少
    —— 这正是「GitHub Actions 上跑得起来吗」那个悬着的问题

━━━ 用法 ━━━
    # 用内置基线（首页 / 积分页 / 登录页 / 站内 .html / 积分接口）
    python -B Selenium/CheckIN/xuexi_page_test.py

    # 换成自己的清单：每行一个 URL，# 开头是注释
    python -B Selenium/CheckIN/xuexi_page_test.py urls.txt

给接口那几条带上登录态（不带也能测，只是会回 401，状态码本身也是信息）：
    XUEXI_COOKIE="token=..." python -B Selenium/CheckIN/xuexi_page_test.py

退出码：全部 2xx 且拿到内容 → 0；有超时/非 2xx/被顶替 → 1。
"""

import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Selenium.CheckIN.xuexi import normalize_cookie  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 基线：PC 端四类入口。不带文章列表 —— 列表要靠运行时接口，属于「内容推送」那一步。
DEFAULT_TARGETS = [
    # (说明, URL, 期望出现的字样)
    ("首页 SPA 壳", "https://www.xuexi.cn/", "<title>学习强国</title>"),
    ("积分页", "https://pc.xuexi.cn/points/my-points.html", "my-points"),
    ("登录页", "https://pc.xuexi.cn/points/login.html", "login"),
    (
        "站内 .html 页",
        "https://www.xuexi.cn/4063dbabf4bad826aeeb5d831ce9624e/"
        "60bd1d03c55149fd0e92da70d074d72b.html",
        "<html",
    ),
    (
        "积分接口",
        "https://pc-proxy-api.xuexi.cn/delegate/score/today/query",
        '"code"',
    ),
]


def load_targets(path):
    """从文件读 URL 清单；返回 [(说明, url, 期望字样)]。"""
    targets = []
    with open(path, encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # 允许 `说明 | url` 的写法，方便在表里认出是谁
            if "|" in line:
                label, url = [x.strip() for x in line.split("|", 1)]
            else:
                label, url = "line%d" % lineno, line
            targets.append((label, url, ""))
    return targets


def probe(label, url, expect, cookie_header=""):
    """发一次 GET，收工。**没有重试、没有 sleep** —— 见文件头的说明。"""
    headers = {"User-Agent": UA, "Referer": "https://pc.xuexi.cn/points/my-points.html"}
    if cookie_header:
        headers["Cookie"] = cookie_header

    started = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except requests.RequestException as err:
        return {
            "label": label,
            "url": url,
            "ok": False,
            "detail": "请求失败: %s" % str(err)[:70],
            "ms": int((time.time() - started) * 1000),
        }
    elapsed = int((time.time() - started) * 1000)

    # ⚠️ 站点不发 charset，requests 会退回 ISO-8859-1，中文标题全变「å­¦ä¹ 」这种乱码，
    #    连「是不是真内容」都没法判。这里显式按 UTF-8 解。
    if "charset" not in (resp.headers.get("Content-Type") or "").lower():
        resp.encoding = "utf-8"
    body = resp.text or ""
    title = ""
    if "<title>" in body:
        title = body.split("<title>", 1)[1].split("</title>", 1)[0].strip()[:26]

    size = len(body)
    detail = "HTTP %d / %s" % (
        resp.status_code,
        ("%dKB" % (size // 1024)) if size >= 1024 else ("%dB" % size),
    )
    if title:
        detail += " / 「%s」" % title

    ok = 200 <= resp.status_code < 300
    if ok and expect and expect not in body:
        ok = False
        detail += " / ✗ 缺特征 %r（可能被顶替）" % expect
    if resp.status_code == 401:
        # 接口不带登录态回 401 是**正常**的：说明站点活着、鉴权在工作，不是网络问题
        detail += " / 未登录（预期行为）"

    return {"label": label, "url": url, "ok": ok, "detail": detail, "ms": elapsed}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    targets = load_targets(path) if path else DEFAULT_TARGETS
    cookie_header = normalize_cookie(os.getenv("XUEXI_COOKIE"))

    print("===> 冒烟测试 %d 个目标（单次请求，不重试、不模拟停留）" % len(targets))
    if cookie_header:
        print("===> 带登录态：Cookie 项 %d 个" % len(cookie_header.split(";")))
    else:
        print("===> 未带登录态：接口那几条会回 401，属正常")

    results = []
    for label, url, expect in targets:
        # 单次 GET，不做任何停留等待
        result = probe(label, url, expect, cookie_header)
        results.append(result)
        print(
            "  %-12s %-6s %5dms  %s"
            % (result["label"][:12], "OK" if result["ok"] else "FAIL", result["ms"], result["detail"])
        )

    bad = [r for r in results if not r["ok"]]
    print("\n==== 结果 ====")
    print("通过 %d / %d" % (len(results) - len(bad), len(results)))
    for r in bad:
        print("[FAIL] %s  %s\n        %s" % (r["label"], r["url"], r["detail"]))
    slowest = max(results, key=lambda r: r["ms"])
    print("最慢一条: %s %dms" % (slowest["label"], slowest["ms"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
