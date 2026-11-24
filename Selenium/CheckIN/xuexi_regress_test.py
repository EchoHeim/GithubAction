# -*- coding: UTF-8 -*-
"""学习强国签到回归测试 —— **全离线**：不联网、不开浏览器、不消耗任何积分。

为什么值得留着：

1. 接口结论是实测推出来的，最容易悄悄改坏的地方全在这儿：
   - `listScoreProgress` 必须传 `deviceType=1`，传 2 只回 4 项 —— 少 14 分，
     而且**不报错**，只是卡片上少几行。这种错看日志看不出来。
   - `totalScore` 是**今日合计**，不是累计；累计要从明细 `list[0].currentScore` 倒推。
   - 强国运动 `periodType=2`（每周），不能算进「今天还差多少」。
2. 「读不到进度」曾经会被判成「登录分未到账」—— 静默的假消息，比报错更坏。

覆盖：T1 Cookie 规整 / T2 数值规整 / T3~T6 接口错误分类 / T7 今日积分 /
T8~T9 进度口径（每日 vs 每周、必须 deviceType=1）/ T10 累计总分倒推 /
T11 卡片 6 行 / T12~T13 凭据缺失 / T14 登录分已到账不开浏览器 /
T15 开页面并回查 0→1 / T16 缺口只算每日项 / T17 进度读失败不得谎报 /
T18 浏览器失败降级 / T19 token 失效仍推失败卡片

跑法（需要装好 selenium / requests，但**不需要** Chrome 和凭据）：
    python -B Selenium/CheckIN/xuexi_regress_test.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import Selenium.CheckIN.xuexi as m  # noqa: E402

# ⚠️ 必须在打补丁之前抓住真函数：m_progress() 本身要用它来解析假响应，
#    否则 qiangguo 测试里 m.read_progress 已被替换成 lambda，会转成无限递归
_REAL_READ_PROGRESS = m.read_progress

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
    return cond


# ───────────────────────── 假响应 ─────────────────────────


class FakeResp:
    def __init__(self, payload, status=200, raw=None):
        self.payload = payload
        self.status_code = status
        self._raw = raw

    @property
    def text(self):
        if self._raw is not None:
            return self._raw
        return json.dumps(self.payload, ensure_ascii=False)

    def json(self):
        if self.payload is None:  # 模拟「返回的是 HTML/纯文本」
            raise ValueError("Expecting value")
        return self.payload


class FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(("GET", url, params))
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        if isinstance(self.resp, Exception):
            raise self.resp
        return self.resp


# 真实任务的快照（2026-11-24 实测）：(标题, 已得, 日上限, periodType)
TASKS = [
    ("趣味答题", 0, 10, 1),
    ("我要选读文章", 1, 12, 1),
    ("订阅", 0, 2, 1),
    ("我要视听学习", 1, 12, 1),
    ("发表观点", 0, 1, 1),
    ("本地频道", 0, 1, 1),
    ("登录", 1, 1, 1),
    ("每日答题", 0, 5, 1),
    ("强国运动", 2, 2, 2),  # ← 每周，别算进当日缺口
]


def progress_payload(tasks=None, black=False, face=False):
    tasks = TASKS if tasks is None else tasks
    rows = [
        {
            "title": title,
            "currentScore": score,
            "dayMaxScore": cap,
            "periodType": period,
            "ruleDesc": "…",
        }
        for title, score, cap, period in tasks
    ]
    return {
        "userId": 151170734596,
        "inBlackList": black,
        "needFaceRecognition": face,
        "totalScore": sum(t[1] for t in tasks),
        "taskProgress": rows,
    }


def login_tasks(login_score):
    """把 TASKS 里的「登录」改成指定分数。"""
    return [(t, login_score if t == "登录" else s, c, p) for t, s, c, p in TASKS]


# ───────────────────────── 隔离：不让测试碰网络/浏览器 ─────────────────────────


class FakeTime:
    def sleep(self, _):
        pass

    def strftime(self, _):
        return "2026-11-24 00:00:00"


def patch(monkey_target, **attrs):
    """给模块打补丁，返回可还原的旧值。"""
    old = {k: getattr(monkey_target, k) for k in attrs}
    for k, v in attrs.items():
        setattr(monkey_target, k, v)
    return old


def restore(monkey_target, old):
    for k, v in old.items():
        setattr(monkey_target, k, v)


def capture_notify():
    box = []

    def fake(bot_id, status, today="", total="", progress="", gap="", account="", note=""):
        box.append(
            dict(
                status=status,
                today=today,
                total=total,
                progress=progress,
                gap=gap,
                account=account,
                note=note,
            )
        )

    return box, fake


def main():
    # T1：Cookie 规整。判据是「名字是不是 token/__UID__」，不是「含不含 =」——
    #     token 值本身可能带 base64 补位，用 `=` 判断会把值当成名字。
    print("[T1] Cookie 规整")
    cases = [
        ("token=abc; __UID__=u1", "token=abc; __UID__=u1"),
        ("  abcdef123456  ", "token=abcdef123456"),
        ("abc123==", "token=abc123=="),  # 裸值含 = ，仍应按值处理
        ("token=abc==", "token=abc=="),
        (";token=x;;", "token=x"),
        ("", ""),
    ]
    for raw, want in cases:
        got = m.normalize_cookie(raw)
        check(got == want, "T1 %r 应为 %r，实得 %r" % (raw, want, got))

    # T2：数值规整。接口把 5 分写成 5.0，卡片上要 5。
    print("[T2] 数值规整")
    for raw, want in [(5.0, 5), ("12", 12), (5.5, 5.5), (None, None), ("x", "x"), (0, 0)]:
        got = m._as_number(raw)
        check(got == want, "T2 %r 应为 %r，实得 %r" % (raw, want, got))

    # T3~T6：接口错误的分类。三种错让用户做的事完全不同，不能混成一句「失败了」。
    print("[T3~T6] 接口错误分类")
    s = FakeSession(FakeResp({"code": 401, "message": "token check failed", "ok": False}))
    try:
        m.call_api(s, m.TODAY_PATH, label="今日积分")
        check(False, "T3 401 应抛 RuntimeError")
    except RuntimeError as err:
        check("token 已失效" in str(err), "T3 401 的报错没点名 token 失效：%s" % err)

    s = FakeSession(FakeResp(None, raw="<html>waf</html>"))
    try:
        m.call_api(s, m.TODAY_PATH, label="今日积分")
        check(False, "T4 非 JSON 应抛 RuntimeError")
    except RuntimeError as err:
        check("不是 JSON" in str(err), "T4 非 JSON 的报错不对：%s" % err)

    s = FakeSession(FakeResp({"code": 500, "message": "boom", "ok": False}))
    try:
        m.call_api(s, m.TODAY_PATH, label="今日积分")
        check(False, "T5 ok=false 应抛 RuntimeError")
    except RuntimeError as err:
        check("返回异常" in str(err), "T5 业务错误的报错不对：%s" % err)

    s = FakeSession(FakeResp({"code": 200, "ok": True, "data": {"score": 5.0}}))
    data = m.call_api(s, m.TODAY_PATH, label="今日积分")
    check(data == {"score": 5.0}, "T6 成功路径应返回 data，实得 %r" % (data,))

    # 网络异常要说是网络，别让人去重扫 token
    s = FakeSession(m.requests.ConnectionError("boom"))
    try:
        m.call_api(s, m.TODAY_PATH, label="今日积分")
        check(False, "T6b 网络异常应抛 RuntimeError")
    except RuntimeError as err:
        check("网络问题" in str(err), "T6b 网络异常应明说是网络问题：%s" % err)

    # T7：今日积分
    print("[T7] 今日积分")
    s = FakeSession(FakeResp({"code": 200, "ok": True, "data": {"score": 5.0}}))
    check(m.read_today_score(s) == 5, "T7 score=5.0 应读成 5")

    # T8：进度口径。**必须传 deviceType=1** —— 传 2 只回 4 项，静默少 14 分。
    print("[T8] 进度口径")
    s = FakeSession(FakeResp({"code": 200, "ok": True, "data": progress_payload()}))
    prog = m.read_progress(s)
    sent = s.calls[-1][2] or {}
    check(sent.get("deviceType") == 1, "T8 必须传 deviceType=1，实际传了 %r" % (sent.get("deviceType"),))
    check(sent.get("sence") == "score", "T8 参数名是 sence（站点拼写错误），实际 %r" % (sent.get("sence"),))
    check(len(prog["tasks"]) == 9, "T8 应解析出 9 项，实得 %d" % len(prog["tasks"]))
    weekly = [t for t in prog["tasks"] if not t["daily"]]
    check(len(weekly) == 1 and weekly[0]["title"] == "强国运动", "T8 只有强国运动是每周项")
    check(prog["total"] == 5, "T8 totalScore 是今日合计 5，实得 %r" % (prog["total"],))

    # T9：账号健康标记 + 结构变化
    print("[T9] 账号状态与结构变化")
    s = FakeSession(
        FakeResp(
            {"code": 200, "ok": True, "data": progress_payload(black=True, face=True)}
        )
    )
    prog = m.read_progress(s)
    check(prog["in_blacklist"] and prog["need_face"], "T9 黑名单/人脸标记没读出来")

    s = FakeSession(FakeResp({"code": 200, "ok": True, "data": ["不是对象"]}))
    try:
        m.read_progress(s)
        check(False, "T9 进度返回数组时应抛 RuntimeError")
    except RuntimeError:
        pass

    # T10：累计总分。没有总分接口，靠明细倒推 —— list[0] 是最近一笔「入账后」的值。
    print("[T10] 累计总分倒推")
    s = FakeSession(
        FakeResp({"code": 200, "ok": True, "data": {"list": [{"currentScore": 752.0}]}})
    )
    check(m.read_total_score(s) == 752, "T10 应取 list[0].currentScore=752")
    check(
        s.calls[-1][0] == "POST" and s.calls[-1][2] == {"pageNo": 1, "pageSize": 1},
        "T10 明细接口应是 POST {pageNo:1,pageSize:1}，实得 %r" % (s.calls[-1],),
    )
    s = FakeSession(FakeResp({"code": 200, "ok": True, "data": {"list": []}}))
    check(m.read_total_score(s) is None, "T10 无记录时应返回 None，不能填 0")

    # T11：卡片。缺口按每日项算，每周项不参与。
    print("[T11] 卡片内容")
    captured = {}

    def fake2(ID, title, content):
        captured.update(title=title, content=content)

    old = patch(m, Feishu_SendCardMsg=fake2)
    try:
        m.notify(
            "hook",
            "今日登录分已到账",
            5,
            752,
            "趣味答题 0/10 ｜ 强国运动 2/2（周）",
            "还差 41 分（3/44，只算每日项）",
            "正常",
            "备注",
        )
    finally:
        restore(m, old)
    body = captured.get("content", "")
    for needle in ("签到状态", "今日积分**: 5 分", "累计积分**: 752 分", "今日缺口", "账号状态", "时间"):
        check(needle in body, "T11 卡片缺 %r 这一行：\n%s" % (needle, body))
    check("（周）" in body, "T11 每周项应带「（周）」标记")

    # 没读到值时要写「未读取到」，不能写 0 分
    old = patch(m, Feishu_SendCardMsg=fake2)
    try:
        m.notify("hook", "x", None, None)
    finally:
        restore(m, old)
    body = captured.get("content", "")
    check(body.count("未读取到") == 2, "T11 缺失值应显示「未读取到」，实得：\n%s" % body)

    # T12~T13：凭据缺失要快失败并说清楚
    print("[T12~T13] 凭据校验")
    for cookie, label in [("", "T12 空 cookie"), ("abc=1; def=2", "T13 没有 token 项")]:
        try:
            m.qiangguo(cookie=cookie, bot_id="")
            check(False, "%s 应 SystemExit" % label)
        except SystemExit as err:
            check("token" in str(err) or "Cookie" in str(err), "%s 的提示没说清原因：%s" % (label, err))

    # T14：登录分已到账 → 不开浏览器（省 30 秒）
    print("[T14] 登录分已到账不开浏览器")
    opened = []
    box, fake = capture_notify()
    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=lambda s: 5,
        read_progress=lambda s: m_progress(progress_payload()),
        read_total_score=lambda s: 752,
        visit_points_page=lambda cookie: opened.append(1) or (True, "u", ""),
        notify=fake,
        time=FakeTime(),
    )
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    finally:
        restore(m, old)
    check(not opened, "T14 登录分 1/1 时不该开浏览器，实际开了 %d 次" % len(opened))
    check(box and box[-1]["status"] == "今日登录分已到账", "T14 状态不对：%r" % (box[-1]["status"],))

    # T15：登录分 0/1 且开了浏览器 → 回查 0→1 才能说「已到账」
    print("[T15] 开页面并回查登录分")
    opened = []
    seq = [m_progress(progress_payload(login_tasks(0))), m_progress(progress_payload(login_tasks(1)))]
    box, fake = capture_notify()

    def fake_progress(_):
        return seq.pop(0) if seq else m_progress(progress_payload(login_tasks(1)))

    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=lambda s: 4,
        read_progress=fake_progress,
        read_total_score=lambda s: 752,
        visit_points_page=lambda cookie: opened.append(1) or (True, "https://pc.xuexi.cn/points/my-points.html", ""),
        notify=fake,
        time=FakeTime(),
    )
    old_env = os.environ.get("XUEXI_BROWSER")
    os.environ["XUEXI_BROWSER"] = "1"
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    finally:
        restore(m, old)
        if old_env is None:
            os.environ.pop("XUEXI_BROWSER", None)
        else:
            os.environ["XUEXI_BROWSER"] = old_env
    check(len(opened) == 1, "T15 登录分 0/1 时应开一次浏览器，实得 %d" % len(opened))
    check(
        box and "登录分已到账" in box[-1]["status"],
        "T15 回查拿到 1/1 后应判「登录分已到账」，实得 %r" % (box[-1]["status"],),
    )

    # T16：缺口只算每日项。强国运动 2/2 不能算成「已达成」，也不能算进上限。
    print("[T16] 缺口只算每日项")
    box, fake = capture_notify()
    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=lambda s: 5,
        read_progress=lambda s: m_progress(progress_payload()),
        read_total_score=lambda s: 752,
        visit_points_page=lambda cookie: (True, "u", ""),
        notify=fake,
        time=FakeTime(),
    )
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    finally:
        restore(m, old)
    gap = box[-1]["gap"]
    check("41" in gap and "3/44" in gap, "T16 缺口应为「还差 41 分（3/44）」，实得 %r" % (gap,))
    check("46" not in gap, "T16 每周项不能算进上限（不能出现 46）")

    # T17：进度读失败时**不许**谎报「登录分未到账」
    print("[T17] 进度读失败不得谎报")
    box, fake = capture_notify()

    def boom(_):
        raise RuntimeError("每日进度接口 500")

    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=lambda s: 5,
        read_progress=boom,
        read_total_score=lambda s: 752,
        visit_points_page=lambda cookie: (True, "u", ""),
        notify=fake,
        time=FakeTime(),
    )
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    finally:
        restore(m, old)
    status = box[-1]["status"]
    check("进度读取失败" in status, "T17 应是「进度读取失败」，实得 %r" % (status,))
    check("未到账" not in status, "T17 读不到进度时不得判「未到账」，实得 %r" % (status,))

    # T18：浏览器失败要降级，不能把整个签到判死
    print("[T18] 浏览器失败降级")
    box, fake = capture_notify()
    seq = [m_progress(progress_payload(login_tasks(0)))]
    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=lambda s: 4,
        read_progress=lambda s: seq.pop(0) if seq else m_progress(progress_payload(login_tasks(0))),
        read_total_score=lambda s: 752,
        visit_points_page=lambda cookie: (False, "", "浏览器步骤失败: chromedriver not found"),
        notify=fake,
        time=FakeTime(),
    )
    os.environ["XUEXI_BROWSER"] = "1"
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    finally:
        restore(m, old)
        os.environ.pop("XUEXI_BROWSER", None)
    check("浏览器未成功" in box[-1]["status"], "T18 应降级为「仅接口校验」，实得 %r" % (box[-1]["status"],))
    check("chromedriver" in box[-1]["note"], "T18 备注应带上失败原因")

    # T19：token 失效 → 抛异常，但仍然推一张失败卡片（不能静默死掉）
    print("[T19] token 失效仍推卡片")
    box, fake = capture_notify()

    def dead(_):
        raise RuntimeError("Cookie 里的 token 已失效（服务端：token check failed）")

    old = patch(
        m,
        make_session=lambda cookie: object(),
        read_today_score=dead,
        read_progress=lambda s: m_progress(progress_payload()),
        read_total_score=lambda s: None,
        visit_points_page=lambda cookie: (True, "u", ""),
        notify=fake,
        time=FakeTime(),
    )
    raised = None
    try:
        m.qiangguo(cookie="token=x", bot_id="hook")
    except RuntimeError as err:
        raised = err
    finally:
        restore(m, old)
    check(raised is not None, "T19 token 失效应抛出，不能吞掉")
    check(box and box[-1]["status"] == "签到失败", "T19 失败时也应推一张「签到失败」卡片")
    check("token 已失效" in (box[-1]["note"] or ""), "T19 卡片备注应写明 token 失效")

    print("\n==== 结果 ====")
    for f in fails:
        print("[FAIL] " + f)
    print("全部通过" if not fails else "有 %d 项失败" % len(fails))
    return 1 if fails else 0


def m_progress(payload):
    """把 payload 过一遍 read_progress 的解析逻辑，得到真实结构。"""

    class _S:
        def get(self, url, params=None, timeout=None):
            return FakeResp({"code": 200, "ok": True, "data": payload})

    return _REAL_READ_PROGRESS(_S())


if __name__ == "__main__":
    sys.exit(main())
