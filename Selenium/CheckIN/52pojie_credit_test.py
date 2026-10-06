# -*- coding: UTF-8 -*-
"""52pojie 吾爱币抽取逻辑的离线回归测试（合成 DOM，不需要登录态）。

⚠️ 为什么要有这个：真实站点验证必须有登录 Cookie，改一次选择器就跑一次真站点
成本太高。这里用 JS 把 52pojie.py 里那份 CREDIT_EXTRACT_JS 原封不动地执行，
喂进「真实结构 + 各种变体 + 陷阱」，确认它挑对了数字、没被旁边的
「贡献值 / 热心值 / 悬赏值 / 总积分」串位。

跑法（需要本机 Chrome + chromedriver）：
    python -B Selenium/CheckIN/52pojie_credit_test.py

只跑纯逻辑那一半（不起浏览器，只校验判定函数）：
    python -B Selenium/CheckIN/52pojie_credit_test.py --offline
"""

import importlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

p52 = importlib.import_module("Selenium.CheckIN.52pojie")

# 把 CREDIT_EXTRACT_JS 装进一个函数体，塞进合成 DOM 里跑
HARNESS = r"""
var html = arguments[0];
var host = document.createElement('div');
host.innerHTML = html;
document.body.appendChild(host);
var saved_ct = document.getElementById('ct');
if (saved_ct) saved_ct.id = '__ct_saved';
host.id = 'ct';
var result = (function(){
%s
})();
host.id = '__host';
if (saved_ct) saved_ct.id = 'ct';
host.parentNode.removeChild(host);
return result;
"""


# 用例：html, 期望值, 说明
CASES = [
    # 1. 截图里的真实结构：标签在 dt，数字在 dd 的 <em> 里
    (
        """
        <div class="credit_setting">
          <dl class="credit_list">
            <dt>吾爱币:</dt><dd><em>413</em> CB <a href="#">帮助</a></dd>
            <dt>贡献值:</dt><dd><em>0</em> 点</dd>
            <dt>热心值:</dt><dd><em>15</em> 点</dd>
            <dt>悬赏值:</dt><dd><em>0</em> 点</dd>
          </dl>
        </div>
        """,
        "413",
        "真实结构：吾爱币在贡献值/热心值之前，不能串位",
    ),
    # 2. 标记全是 class=credit_num（Discuz 老模板）
    (
        """
        <table class="credit_num_table">
          <tr><td class="credit_num">413</td><td>吾爱币</td></tr>
          <tr><td class="credit_num">0</td><td>贡献值</td></tr>
        </table>
        """,
        "413",
        "credit_num 精确类名优先",
    ),
    # 3. 一行纯文本
    (
        """<p class="credit_line">吾爱币: 413 CB</p>""",
        "413",
        "同一文本节点内联",
    ),
    # 4. 千分位
    (
        """<p class="credit_line">吾爱币: 1,413 CB</p>""",
        "1413",
        "千分位要吃掉",
    ),
    # 5. 陷阱：贡献值/热心值排在吾爱币**之前**（顺序反了会不会串位）
    (
        """
        <dl>
          <dt>贡献值:</dt><dd><em>0</em> 点</dd>
          <dt>热心值:</dt><dd><em>15</em> 点</dd>
          <dt>吾爱币:</dt><dd><em>413</em> CB</dd>
        </dl>
        """,
        "413",
        "吾爱币在后，前面的一堆点值不能抢先",
    ),
    # 6. 陷阱：页头/右侧栏的「积分: 57」在旁边晃
    (
        """
        <div>积分: 57</div>
        <dl><dt>吾爱币:</dt><dd><em>413</em> CB</dd></dl>
        """,
        "413",
        "不能把总积分 57 当成吾爱币",
    ),
]


def run_offline_checks():
    """不需要浏览器的部分。"""
    failed = []

    # 吾爱币正则本身的行为
    import re

    def coin(text):
        m = re.search(r"吾爱币[:：]?\s*(\d[\d,]*)", text)
        return m.group(1).replace(",", "") if m else ""

    for text, expect in [
        ("吾爱币: 413 CB", "413"),
        ("吾爱币：413 CB", "413"),
        ("吾爱币 413", "413"),
        ("吾爱币: 1,413 CB", "1413"),
        ("贡献值: 0 点 吾爱币: 413 CB", "413"),
        ("积分: 57", ""),
    ]:
        got = coin(text)
        mark = "OK " if got == expect else "FAIL"
        if got != expect:
            failed.append("吾爱币正则 %r → %r，期望 %r" % (text, got, expect))
        print("  [%s] 正则 %r → %r" % (mark, text, got))

    # notify() 的卡片文案
    import io
    from contextlib import redirect_stdout

    sent = {}

    def fake_send(bot_id, title, content):
        sent["title"] = title
        sent["content"] = content
        return None

    original = p52.Feishu_SendCardMsg
    p52.Feishu_SendCardMsg = fake_send
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            p52.notify("https://example.invalid/hook", "签到成功",
                       "", "57", "回帖成功（pid=1 page=1）", "413")
    finally:
        p52.Feishu_SendCardMsg = original

    card = sent.get("content", "")
    for needle, label in [
        ("**签到状态**: 签到成功", "签到状态"),
        ("**当前积分**: 57", "当前积分"),
        ("**吾爱币**: 413 CB", "吾爱币带 CB 单位"),
        ("**回帖**: 回帖成功", "回帖"),
    ]:
        mark = "OK " if needle in card else "FAIL"
        if needle not in card:
            failed.append("卡片缺 %r" % needle)
        print("  [%s] 卡片含 %s" % (mark, label))

    # 吾爱币读不到时不能显示成空白
    sent.clear()
    p52.Feishu_SendCardMsg = fake_send
    try:
        with redirect_stdout(io.StringIO()):
            p52.notify("https://example.invalid/hook", "签到成功", "", "57", "", "")
    finally:
        p52.Feishu_SendCardMsg = original
    card = sent.get("content", "")
    mark = "OK " if "**吾爱币**: 未读取到" in card else "FAIL"
    if "**吾爱币**: 未读取到" not in card:
        failed.append("吾爱币为空时未显示「未读取到」")
    print("  [%s] 吾爱币为空 → 未读取到" % mark)

    return failed


def run_browser_checks():
    """真实 DOM 抽取：用合成 HTML 喂给线上那份 JS。"""
    from Selenium.base import get_web_driver

    failed = []
    driver = get_web_driver()
    try:
        driver.get("about:blank")
        body = p52.CREDIT_EXTRACT_JS
        script = HARNESS % body
        for html, expect, note in CASES:
            got = driver.execute_script(script, html)
            got = (got or "").strip()
            mark = "OK " if got == expect else "FAIL"
            if got != expect:
                failed.append("用例 %r：得到 %r，期望 %r" % (note, got, expect))
            print("  [%s] %-40s → %r (期望 %r)" % (mark, note, got, expect))
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    return failed


def main():
    offline_only = "--offline" in sys.argv

    print("=== 离线检查（纯逻辑）===")
    failed = run_offline_checks()

    if not offline_only:
        print("\n=== 合成 DOM 检查（真 Chrome 执行线上那份 JS）===")
        try:
            failed += run_browser_checks()
        except Exception as err:
            print("  [SKIP] 起不了浏览器: %s" % err)
            print("  （加 --offline 只跑纯逻辑那部分）")

    print()
    if failed:
        print("[X] %d 项失败:" % len(failed))
        for item in failed:
            print("    - %s" % item)
        return 1
    print("[✓] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
