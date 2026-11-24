# -*- coding: UTF-8 -*-
"""学习强国「今日阅读清单」—— 挑 10 篇互不相同的文章，**给人读**，不是给脚本读。

━━━ 为什么是清单不是自动阅读 ━━━
「选读文章」那 12 分来自「阅读」这个行为本身：篇数分按篇去重、时长分按正文页停留累计。
脚本挂 30 秒、循环 10 篇，平台记下的就是 10 条「有效阅读」—— 那是制造记录，不是测试。
所以这个脚本只做**选**这件事：从官方列表接口按栏目抽 10 篇，把标题和链接摆出来，
你点开读，分自然到手。省的是「找什么读」的时间，不是「读」。

━━━ 数据从哪来 ━━━
`https://www.xuexi.cn/lgdata/<栏目hash>.json` 是站点自己的列表数据（首页 SPA 拉的也是这个），
一份 4.6MB，7000+ 条，字段含 title / url / publishTime / channelNames / itemId。

⚠️ 这是**单一栏目**的列表（实测 42 个 channelNames，其中「头条新闻」占 6316 条），
不是全站聚合。首页那 16 个 `array-channel!*.json` 分片的真实基址没探到
（/lgdata、bootcdn、source 下都 404），所以清单的栏目分布天然偏向要闻 —— 够读，
但别指望它像 App 首页那样什么频道都有。

━━━ 用法 ━━━
    python -B Selenium/CheckIN/xuexi_reading_list.py              # 10 篇，近 3 天
    python -B Selenium/CheckIN/xuexi_reading_list.py 10 7         # 10 篇，近 7 天
    FEISHU_BOT_ID=https://... python -B Selenium/CheckIN/xuexi_reading_list.py   # 顺带推卡片

退出码：正常 0；接口挂了 1。
"""

import datetime
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 文章列表（要闻类，实测 7050 条）与视频/音频列表
ARTICLE_LIST = "https://www.xuexi.cn/lgdata/1crqb964p71.json"
VIDEO_LIST = "https://www.xuexi.cn/lgdata/1novbsbi47k.json"


def fetch_items(url):
    """拉一份列表数据。站点不发 charset，得显式按 UTF-8 解，否则标题全是乱码。"""
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    if "charset" not in (resp.headers.get("Content-Type") or "").lower():
        resp.encoding = "utf-8"
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError("列表接口返回的不是数组：%s" % type(data).__name__)
    return data


def normalize(item):
    """统一成 {title, url, when, channel} —— 两个列表字段名一致，顺手挡掉缺字段的行。"""
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    if not title or not url:
        return None
    names = item.get("channelNames") or []
    return {
        "title": title,
        "url": url,
        "when": (item.get("publishTime") or "")[:16],
        "channel": (names[0] if names else "未分类"),
        "day": (item.get("publishTime") or "")[:10],
        "id": item.get("itemId") or url,
    }


def pick(items, count, days):
    """最近 `days` 天、按栏目轮流取，保证 10 篇互不相同且尽量分散。

    去重按 itemId（同一篇会同时在多个栏目里出现，光比标题不够）；
    分桶按 channelNames[0]，桶之间按最新时间排序后轮询 —— 先每栏拿 1 篇，
    不够再回头拿第 2 轮。这样栏目分布比「按时间倒序取前 10」均匀得多。
    """
    since = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    seen = set()
    buckets = {}
    for raw in items:
        item = normalize(raw)
        if not item or item["id"] in seen:
            continue
        if item["day"] < since:
            continue
        seen.add(item["id"])
        buckets.setdefault(item["channel"], []).append(item)

    for rows in buckets.values():
        rows.sort(key=lambda r: r["when"], reverse=True)
    # 桶之间按各自最新一篇的时间排序，让「最近有更新」的栏目先出场
    order = sorted(buckets.items(), key=lambda kv: kv[1][0]["when"], reverse=True)

    picked = []
    round_no = 0
    while len(picked) < count:
        added = False
        for _, rows in order:
            if round_no < len(rows):
                picked.append(rows[round_no])
                added = True
                if len(picked) >= count:
                    break
        if not added:  # 所有桶都取空了
            break
        round_no += 1
    return picked


def pick_with_widen(items, count, days):
    """近 `days` 天不够 `count` 篇时自动放宽窗口，返回 (picked, 实际窗口)。

    实测这份列表日更量很低（近 3 天只有 2 条），死守 3 天的话日报会只剩两条，
    那就失去意义了。宁可放宽到一周，也要凑够一屏能看的量。
    """
    picked, window = [], days
    for factor in (1, 2, 4, 10):
        window = days * factor
        picked = pick(items, count, window)
        if len(picked) >= count:
            return picked, window
    return picked, window


def render(picked, days):
    lines = [
        "===> 最近 %d 天共挑出 %d 篇（按栏目轮流取，不重复）" % (days, len(picked)),
    ]
    for idx, item in enumerate(picked, 1):
        lines.append("")
        lines.append("%2d. [%s] %s" % (idx, item["channel"], item["title"]))
        lines.append("    %s  %s" % (item["when"], item["url"]))
    return "\n".join(lines)


def to_card(picked):
    """飞书 lark_md：`[标题](链接)` 可以点。按栏目分组排版，比纯序号好扫。"""
    rows = ["**最近更新 · %d 篇**" % len(picked), ""]
    for idx, item in enumerate(picked, 1):
        rows.append("%d. **[%s]** %s" % (idx, item["channel"], item["title"]))
        rows.append("    [打开](%s)" % item["url"])
    return "\n".join(rows)


def _int_arg(argv, index, default):
    """取一个正整数参数；空串/非数字/0 都退回默认值。

    workflow 里参数来自 `${{ inputs.count || '10' }}`，手工触发时留空会传空串 ——
    直接 int('') 会甩一屏 traceback，而这里最合适的行为就是用默认值继续跑。
    """
    try:
        value = int(str(argv[index]).strip())
    except (IndexError, ValueError):
        return default
    return value if value > 0 else default


def main():
    count = _int_arg(sys.argv, 1, 10)
    days = _int_arg(sys.argv, 2, 3)

    print("===> 拉列表: %s" % ARTICLE_LIST)
    items = fetch_items(ARTICLE_LIST)
    print("===> 共 %d 条" % len(items))
    try:
        video = fetch_items(VIDEO_LIST)
        items = items + video
        print("===> 并入视听列表 %d 条" % len(video))
    except Exception as err:
        print("[WARN] 视听列表拉取失败（不影响文章清单）: %s" % err)

    picked, window = pick_with_widen(items, count, days)
    if not picked:
        print("[X] 近 %d 天没有可用条目 —— 把天数放大试试：%s %d 7" % (days, sys.argv[0], count))
        return 1
    if window != days:
        print(
            "===> 近 %d 天不够 %d 篇，已放宽到 %d 天" % (days, count, window)
        )

    print(render(picked, window))

    bot_id = os.getenv("FEISHU_BOT_ID") or ""
    if bot_id:
        from Messaging.Feishu import Feishu_SendCardMsg

        Feishu_SendCardMsg(bot_id, " 学习强国 · 今日阅读清单 ", to_card(picked))
    else:
        print("\n（没给 FEISHU_BOT_ID，只打印不推送）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
