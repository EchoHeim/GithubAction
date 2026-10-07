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
import re
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

    failed += _check_reply_judging()
    failed += _check_pick_threads()

    return failed


# ── 挑帖去重（2026-10-07 加）────────────────────────────────────────────────
# lodge 要求「回两个不同的帖子」。这里锁住关键不变式：
#   1. 同一 tid 只算一个候选（列表里可能重复出现）；
#   2. 挑出来的 N 个必须是 N 个**不同**的帖子 —— 挑重了等于「对同一个帖回两次」，
#      Discuz 会拦（重复回复），更糟的是这就成了刷帖；
#   3. 候选不够就报错，**绝不降级成重复回同一个**。
def _check_pick_threads():
    failed = []

    # 假 driver：只实现 pick_threads 用到的两个方法
    class FakeDriver:
        def __init__(self, links):
            self._links = links

        def find_elements(self, by, xpath):
            return [FakeLink(href, text) for href, text in self._links]

    class FakeLink:
        def __init__(self, href, text):
            self._href = href
            self._text = text

        def get_attribute(self, name):
            return self._href if name == "href" else None

        @property
        def text(self):
            return self._text

    def with_tid(n, title):
        return ("https://www.52pojie.cn/thread-%d-1-1.html" % n, title)

    # 3 个不同帖子 + 2 个重复项（同一 tid 再出现一次）
    links = [
        with_tid(100, "帖子A"),
        with_tid(100, "帖子A 重复项"),
        with_tid(200, "帖子B"),
        with_tid(300, "帖子C"),
        with_tid(200, "帖子B 又来一次"),
    ]

    # pick_threads 前半段是「开页面 + 过 WAF」，与去重逻辑无关且要真浏览器。
    # 只 monkeypatch 掉这部分 —— 测试要验的是去重/抽样/兜底，不是网络。
    original_pass_waf = p52.pass_waf
    original_wait_ready = p52.wait_document_ready
    original_dump = p52.dump_debug
    p52.pass_waf = lambda driver, url, **kw: True
    p52.wait_document_ready = lambda driver, timeout=15: True
    p52.dump_debug = lambda *a, **kw: None
    try:
        picked = p52.pick_threads(FakeDriver(links), "https://x/forum-16-1.html", 2)
        tids = [re.search(r"thread-(\d+)-", h).group(1) for _, h in picked]
        mark = "OK " if len(set(tids)) == 2 else "FAIL"
        if len(set(tids)) != 2:
            failed.append("挑了 2 个帖子但有重复: %r" % tids)
        print("  [%s] 重复项被去重、挑出 2 个不同帖子 → tid %s" % (mark, tids))

        # 候选只有 1 个，却要 2 个 → 必须报错，不能拿同一个凑数
        only_one = [with_tid(100, "帖子A"), with_tid(100, "帖子A 重复项")]
        try:
            p52.pick_threads(FakeDriver(only_one), "https://x/forum-16-1.html", 2)
            failed.append("候选不足时没有报错（会变成重复回同一个帖）")
            print("  [FAIL] 候选不足时应抛错")
        except RuntimeError as err:
            mark = "OK " if "不够" in str(err) else "FAIL"
            if "不够" not in str(err):
                failed.append("候选不足的报错没说明原因: %s" % err)
            print("  [%s] 候选不足 → 拒绝而非重复回帖: %s" % (mark, str(err)[:50]))

        # count=0 是合法的「不回」，不该报错
        try:
            empty = p52.pick_threads(FakeDriver(links), "https://x/forum-16-1.html", 0)
            mark = "OK " if empty == [] else "FAIL"
            if empty != []:
                failed.append("count=0 应返回空列表")
            print("  [%s] count=0 → 直接返回空列表" % mark)
        except Exception as err:
            failed.append("count=0 不该抛错: %s" % err)
            print("  [FAIL] count=0 抛错: %s" % err)
    finally:
        p52.pass_waf = original_pass_waf
        p52.wait_document_ready = original_wait_ready
        p52.dump_debug = original_dump

    return failed


# ── 回帖判定（2026-10-07 加）────────────────────────────────────────────────
# 背景：CI 上服务端明确回了「抱歉，您的请求来路不正确或表单验证串不符，无法提交」
#（Discuz submitcheck() 的 formhash 校验失败），但日志报出来的是
# `var STYLEID = '1', STA` —— 那是 Discuz 提示页 head 里的 JS 变量，跟报错无关。
# 原因是 _reply_snippet 靠「marker 往前取上下文 + 按标签收尾」定位句子，
# 在「所有 <script> 都拼进 blob」的前提下会抓到隔壁的 JS。
#
# 这几条断言锁住三件事：
#   1. 报错原话能完整露出来（不再被剪成 var STYLEID）；
#   2. formhash 类拒绝归到formhash，不被「抱歉，您」兜底吃掉；
#   3. 分类是纯函数、离线可测（真站点要 Cookie 才有资格验）。
def _check_reply_judging():
    failed = []

    def check(label, got, expect):
        mark = "OK " if got == expect else "FAIL"
        if got != expect:
            failed.append("%s：得到 %r，期望 %r" % (label, got, expect))
        print("  [%s] %s → %r" % (mark, label, got))

    # 1) 复刻真实结构：head 里一堆 <script>（含 STYLEID），正文 #messagetext 是真因
    blob = (
        "var STYLEID = '1', STATICURL = 'static/image/', IMGDIR = 'static/image/';\n"
        "var discuz_uid = '12345';\n"
        "<div id=\"messagetext\" class=\"alert_error\">"
        "抱歉，您的请求来路不正确或表单验证串不符，无法提交</div>"
    )
    kind, detail = p52.classify_reply_blob(blob)
    check("真因含「请求来路不正确」", kind, "formhash")
    # 句子从命中的 marker 起算，所以不含「抱歉，您」这个客套前缀 —— 无信息损失，
    # 关键是「请求来路不正确或表单验证串不符，无法提交」这一整句都在。
    check(
        "回执整句露出来",
        detail,
        "请求来路不正确或表单验证串不符，无法提交",
    )
    if "STYLEID" in detail:
        failed.append("回执里混进了 head 的 JS 变量：%r" % detail)

    # 2) 只有泛短语「抱歉，您」时归 error，不能冒充 formhash
    kind, _ = p52.classify_reply_blob(
        "<em id='returnmessage_x'>抱歉，您的两次发表间隔少于 15 秒</em>"
    )
    check("间隔太短归 error", kind, "error")

    # 3) 审核类仍归 pending（别被formhash 判定抢走）
    kind, _ = p52.classify_reply_blob("您发表的回复需要审核，审核通过后将会显示")
    check("待审核归 pending", kind, "pending")

    # 4) 成功回执
    kind, detail = p52.classify_reply_blob(
        "succeedhandle_fastpost('forum.php?mod=redirect&goto=findpost&pid=998877&ptid=123')"
    )
    check("成功回执", kind, "success")
    check("成功带 pid", detail, "pid=998877 page=?")

    # 5) 基线差分：页面固有文本里的「抱歉，您」不算本次错误
    base = "<div class='tip'>抱歉，您当前是游客身份</div>"
    kind, _ = p52.classify_reply_blob(base, baseline=base)
    check("固有文本不误判", kind, "none")

    # 6) 服务端成功后紧跟一句「请求来路不正确」（极少见，但要保证不被formhash 抢走成功）
    kind, _ = p52.classify_reply_blob(
        "抱歉，您的请求来路不正确或表单验证串不符，无法提交\nsucceedhandle_fastpost('x')"
    )
    check("成功优先于 formhash", kind, "success")

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
