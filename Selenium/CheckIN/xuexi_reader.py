# -*- coding: UTF-8 -*-
"""学习强国「本地阅读器」—— 用浏览器读，但读的是本地页面。

━━━ 它是什么 ━━━
一次抓 N 篇正文（HTTP 直取 JSONP），渲染成一个单文件 HTML，用默认浏览器打开。
顶部是目录，下面是正文，键盘 `j`/`k` 翻篇、`t` 回目录。

━━━ 它不是什么 ━━━
**不访问学习强国的文章页。** 所有内容来自 `boot-source.xuexi.cn/data/app/<id>.js`
这个静态数据接口，拿到的是文字，不是页面，也不会触发任何上报。
所以你在这里读多久，平台那边都不会记时长 —— 这里没有「记录」这回事，只有读。

想要积分就回官方页面读，那是另一条路；这个工具解决的是「在电脑上读得舒服点」。

━━━ 用法 ━━━
    python -B Selenium/CheckIN/xuexi_reader.py            # 10 篇，近 3 天，自动打开浏览器
    python -B Selenium/CheckIN/xuexi_reader.py 20 7       # 20 篇，近 7 天
    python -B Selenium/CheckIN/xuexi_reader.py 10 3 --no-open   # 只生成不打开

产物：仓库根目录 `xuexi-reading.html`（已 gitignore）。
"""

import html
import os
import re
import sys
import time
import webbrowser

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from Selenium.CheckIN.xuexi_reading_list import pick_with_widen, fetch_items, ARTICLE_LIST  # noqa: E402

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DETAIL_URL = "https://boot-source.xuexi.cn/data/app/%s.js"
OUT_FILE = "xuexi-reading.html"


def fetch_detail(item_id):
    """JSONP `callback({...})` → dict。"""
    resp = requests.get(
        DETAIL_URL % item_id, headers={"User-Agent": UA}, timeout=25
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    raw = resp.text
    start, end = raw.find("("), raw.rfind(")")
    if start < 0 or end <= start:
        raise RuntimeError("不是 JSONP：%s" % raw[:60])
    return __import__("json").loads(raw[start + 1 : end])


def clean_body(content_html):
    """正文 HTML 洗一遍：去脚本/样式/事件属性，保留段落和图片。

    内容来自自家 CDN，但仍按不可信处理 —— 这个页面是用 file:// 打开的，
    里面混进一段 <script> 就等于在本机执行了别人的代码。
    """
    body = content_html or ""
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S | re.I)
    body = re.sub(r"<iframe.*?</iframe>", "", body, flags=re.S | re.I)
    # 事件属性：onclick= / onerror= 这类
    body = re.sub(r"\son[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", body)
    # javascript: 协议
    body = re.sub(r"javascript:", "", body, flags=re.I)
    # 站点自己的内联排版类会带奇怪字号，去掉 style/class 让本地 CSS 接管
    body = re.sub(r"\s(style|class)\s*=\s*(\"[^\"]*\"|'[^']*')", "", body)
    return body.strip() or "<p>（本篇没有正文）</p>"


PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>学习强国 · 本地阅读器（%(count)d 篇）</title>
<style>
  :root { --fg:#1a1a1a; --muted:#6b7280; --line:#e5e7eb; --bg:#fbfbfa; --card:#fff; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg);
         font:16px/1.85 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }
  .wrap { max-width: 760px; margin: 0 auto; padding: 28px 22px 80px; }
  .topbar { position:sticky; top:0; z-index:9; background:rgba(251,251,250,.94);
            backdrop-filter:blur(6px); border-bottom:1px solid var(--line);
            margin:0 -22px 24px; padding:12px 22px; display:flex; gap:14px; align-items:center; }
  .topbar b { font-size:14px; }
  .topbar span { color:var(--muted); font-size:13px; }
  .topbar a { margin-left:auto; font-size:13px; color:#2563eb; text-decoration:none; }
  h1 { font-size:26px; line-height:1.45; margin:0 0 10px; }
  .meta { color:var(--muted); font-size:13px; margin-bottom:22px; }
  article { background:var(--card); border:1px solid var(--line); border-radius:12px;
            padding:34px 34px 26px; margin-bottom:26px; }
  article p { margin:0 0 16px; text-align:justify; }
  article img { max-width:100%%; height:auto; border-radius:8px; display:block; margin:18px auto; }
  .toc { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:20px 26px; }
  .toc h2 { font-size:15px; color:var(--muted); margin:0 0 12px; font-weight:600; }
  .toc ol { margin:0; padding-left:22px; }
  .toc li { margin:8px 0; }
  .toc a { color:var(--fg); text-decoration:none; border-bottom:1px solid var(--line); }
  .toc a:hover { border-color:#2563eb; color:#2563eb; }
  .src { color:var(--muted); font-size:13px; }
  kbd { background:#eee; border-radius:4px; padding:1px 5px; font-size:12px; }
</style></head><body><div class="wrap">
<div class="topbar"><b>本地阅读器</b><span>%(count)d 篇 · 抓取于 %(stamp)s</span>
<a href="#toc">目录</a></div>
<div class="toc" id="toc"><h2>目录（<kbd>j</kbd> 下一篇 / <kbd>k</kbd> 上一篇）</h2><ol>%(toc)s</ol></div>
%(articles)s
</div>
<script>
  var ids = Array.prototype.map.call(document.querySelectorAll('article'), function (a) { return a.id; });
  var cur = -1;
  function go(i) {
    if (i < 0 || i >= ids.length) return;
    cur = i;
    document.getElementById(ids[i]).scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'j') go(Math.min(cur + 1, ids.length - 1));
    if (e.key === 'k') go(Math.max(cur - 1, 0));
    if (e.key === 't') document.getElementById('toc').scrollIntoView({behavior: 'smooth'});
  });
</script>
</body></html>"""


def _int_arg(argv, index, default):
    try:
        value = int(str(argv[index]).strip())
    except (IndexError, ValueError):
        return default
    return value if value > 0 else default


def main():
    count = _int_arg(sys.argv, 1, 10)
    days = _int_arg(sys.argv, 2, 3)
    no_open = "--no-open" in sys.argv

    items, window = pick_with_widen(fetch_items(ARTICLE_LIST), count, days)
    print("===> 选稿 %d 篇（窗口 %d 天），开始取正文" % (len(items), window))

    toc, blocks = [], []
    for idx, item in enumerate(items, 1):
        anchor = "a%d" % idx
        title, body, source, when = item["title"], "", "", item["when"]
        try:
            detail = fetch_detail(item["id"])
            title = detail.get("title") or title
            body = clean_body(detail.get("content"))
            source = detail.get("orig_source") or detail.get("show_source") or item["channel"]
            when = (detail.get("publish_time") or item["when"])[:16]
        except Exception as err:
            print("[WARN] 第 %d 篇取不到正文: %s" % (idx, str(err)[:70]))
            body = "<p>（本篇正文抓取失败，可点原文链接）</p>"

        toc.append(
            '<li><a href="#%s">%s</a> <span class="src">· %s</span></li>'
            % (anchor, html.escape(title), html.escape(source))
        )
        blocks.append(
            '<article id="%s"><h1>%s</h1><div class="meta">%s · %s · '
            '<a href="%s" target="_blank" rel="noreferrer">原文</a></div>%s</article>'
            % (
                anchor,
                html.escape(title),
                html.escape(source),
                html.escape(when),
                item["url"],
                body,
            )
        )
        print("%2d. %s" % (idx, title))
        time.sleep(0.3)

    doc = PAGE % {
        "count": len(blocks),
        "stamp": time.strftime("%Y-%m-%d %H:%M"),
        "toc": "\n".join(toc),
        "articles": "\n".join(blocks),
    }
    path = os.path.abspath(OUT_FILE)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(doc)
    print("\n===> 已生成 %s（%d KB）" % (path, len(doc.encode("utf-8")) // 1024))

    if not no_open:
        webbrowser.open("file:///" + path.replace("\\", "/"))
        print("===> 已用默认浏览器打开")
    return 0


if __name__ == "__main__":
    sys.exit(main())
