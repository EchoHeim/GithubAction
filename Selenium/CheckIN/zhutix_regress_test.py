# -*- coding: UTF-8 -*-
"""致美化签到回归测试 —— **全离线**：不联网、不需要凭据、不碰真站点。

为什么值得留着：

1. 「签到成功」这条判定最容易写歪。B2 的 `task.js` 自己就是乐观派 ——
   `userMission` 一返回就把前端的 `finish` 写死成 1，从不回读服务端。
   照抄它，脚本会在签到被拒时照样报成功。所以这里锁死：
   **只有回查 finish 涨了才算成功**（T5），接口 200 不算。
2. 站点公告「签到功能暂时下线」。把「站点关了」和「我们挂错了」混成一个红叉，
   会让人对着一个不是 bug 的 bug 修半天。判据必须是**接口拒绝 + 公告仍在**两个同时成立（T7/T8）。
3. 登录态被拒（403 请先登录）不该甩一坨 traceback —— CI 日志要的是能照着做的提示（T9）。

覆盖：T1~T2 凭据规整 / T3 找签到项 / T4 已签到不重复调 / T5 签到成功 /
T6 调用报错但回查涨了 / T7 站点下线 / T8 真失败 / T9 登录态被拒 /
T10 卡片内容 / T11 任务表里没有签到项

跑法：
    python -B Selenium/CheckIN/zhutix_regress_test.py
"""

import json
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import Selenium.CheckIN.zhutix as m  # noqa: E402

GOOD_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJkYXRhIjp7InVzZXIiOnsiaWQiOjF9fX0.sig"

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)
    return cond


# ───────────────────────── 假响应 ─────────────────────────


def task_payload(finish=0, times=1):
    """仿 getTaskData 的真实结构（任务是个 dict，key → 任务对象）。"""
    return {
        "task": {
            "task_post": {"name": "发布文章", "finish": 0, "times": 1, "credit": 10},
            "task_comment": {"name": "评论", "finish": 2, "times": 6, "credit": 1},
            "task_mission": {"name": "签到", "finish": finish, "times": times, "credit": 1},
        },
        "task_user": [],
    }


class FakeAPI(object):
    """按 action 返回预设响应，并记下调用顺序。"""

    def __init__(self, tasks_seq, mission_error=None, auth_fail=False, summary=None):
        self.tasks_seq = list(tasks_seq)
        self.mission_error = mission_error
        self.auth_fail = auth_fail
        # 照抄 getUserMission 的真实结构：天数埋在 mission.tk.days，锋币叫 my_credit
        self.summary = (
            summary if summary is not None
            else {"my_credit": 12, "tk": {"days": 3, "credit": 1}, "current_user": 7}
        )
        self.calls = []

    def __call__(self, session, action, label):
        self.calls.append(action)
        if action == "getTaskData":
            if self.auth_fail:
                raise m.AuthError("读取任务列表 拒绝：请先登录（HTTP 403）")
            if not self.tasks_seq:
                raise AssertionError("getTaskData 被调用次数超过了预设序列")
            # 回查会重试多次：只剩最后一个时重复它，模拟「一直读到同一个旧值」
            return self.tasks_seq.pop(0) if len(self.tasks_seq) > 1 else self.tasks_seq[0]
        if action == "userMission":
            if self.mission_error:
                raise self.mission_error
            return {"mission": {}}
        if action == "getUserMission":
            return {"mission": self.summary}
        raise AssertionError("未预期的接口: %s" % action)


def run(fake, cookie=GOOD_TOKEN, offline=False, bot_id="https://example.invalid/bot"):
    """跑一遍 zhutix()，返回 (退出码, 卡片参数, 接口调用顺序)。

    bot_id 默认给个占位值：不填 notify 根本不会被调用，卡片断言就全变成 None 了
    （第一版就是这么踩的 —— 逻辑全对，测试却报了一屏红）。
    """
    captured = {}

    def fake_notify(bot, status, days="", credit="", progress="", note=""):
        captured.update(
            {"status": status, "days": days, "credit": credit, "progress": progress, "note": note}
        )

    patches = [
        mock.patch.object(m, "make_session", lambda token: "FAKE-SESSION"),
        mock.patch.object(m, "call_api", fake),
        mock.patch.object(m, "site_offline", lambda session: offline),
        mock.patch.object(m, "notify", fake_notify),
        # 签到后要等 1.5 秒再回查，测试里不必真等
        mock.patch.object(m.time, "sleep", lambda *_: None),
    ]
    for patch in patches:
        patch.start()

    code = 0
    try:
        m.zhutix(cookie=cookie, bot_id=bot_id)
    except SystemExit as exit_signal:
        raw = exit_signal.code
        code = 0 if raw is None else (raw if isinstance(raw, int) else 1)
    finally:
        for patch in patches:
            patch.stop()
    return code, captured, fake.calls


# ───────────────────────── T1~T2 凭据规整 ─────────────────────────


def test_token_normalize():
    full_cookie = "b2_token=%s; wordpress_logged_in_abc=xyz; PHPSESSID=1" % GOOD_TOKEN
    token, how = m.normalize_token(full_cookie)
    check(token == GOOD_TOKEN, "T1 整行 cookie 应抠出 b2_token，实得 %r（%s）" % (token, how))

    token, how = m.normalize_token("  " + GOOD_TOKEN + "  ")
    check(token == GOOD_TOKEN, "T1 裸 token 应原样保留，实得 %r（%s）" % (token, how))

    token, how = m.normalize_token("wordpress_logged_in_abc=xyz; PHPSESSID=1")
    check(token == "", "T1 无关 cookie 不该硬凑出 token")
    check("没有 b2_token" in how, "T1 无关 cookie 的说明要点名缺 b2_token，实得 %r" % how)

    token, _ = m.normalize_token("")
    check(token == "", "T1 空值应返回空 token")


def test_as_int():
    check(m.as_int("1") == 1, "T2 字符串 '1' 应转 1")
    check(m.as_int(0) == 0, "T2 整数 0 应保持 0")
    check(m.as_int(None, 5) == 5, "T2 None 应退回默认值")
    check(m.as_int("abc", 2) == 2, "T2 非数字应退回默认值")


# ───────────────────────── T3 找签到项 ─────────────────────────


def test_find_mission():
    key, item = m.find_mission(task_payload())
    check(key == "task_mission", "T3 应命中 task_mission，实得 %r" % key)
    check(item and item["name"] == "签到", "T3 应取到签到项")

    # 站点换 key 名也能按 name 找回来
    renamed = {"task": {"task_sign": {"name": "每日签到", "finish": 0, "times": 1}}}
    key, item = m.find_mission(renamed)
    check(key == "task_sign", "T3 换 key 后应按 name 命中，实得 %r" % key)

    key, item = m.find_mission({"task": {"task_post": {"name": "发布文章"}}})
    check(item is None, "T3 没有签到项时应返回 None")

    key, item = m.find_mission({})
    check(item is None, "T3 空结构不该炸")


# ───────────────────────── T4~T8 主流程 ─────────────────────────


def test_already_signed():
    fake = FakeAPI([task_payload(finish=1, times=1)])
    code, card, calls = run(fake)
    check(code == 0, "T4 已签到应退出 0，实得 %s" % code)
    check("userMission" not in calls, "T4 已签到不该再调 userMission，实得 %s" % calls)
    check("今日已签到" in card.get("status", ""), "T4 状态应为今日已签到，实得 %r" % card.get("status"))


def test_sign_success():
    fake = FakeAPI([task_payload(finish=0, times=1), task_payload(finish=1, times=1)])
    code, card, calls = run(fake)
    check(code == 0, "T5 签到成功应退出 0，实得 %s" % code)
    check(calls.count("getTaskData") == 2, "T5 必须回查一次，实得 %s" % calls)
    check("签到成功" in card.get("status", ""), "T5 状态应为签到成功，实得 %r" % card.get("status"))


def test_mission_error_but_finish_grew():
    """接口报错但回查涨了 —— 以回查为准，别被错误文案带偏。"""
    fake = FakeAPI(
        [task_payload(finish=0), task_payload(finish=1)],
        mission_error=RuntimeError("签到 返回异常：HTTP 500"),
    )
    code, card, _ = run(fake)
    check(code == 0, "T6 回查涨了就该判成功，实得退出码 %s" % code)
    check("签到成功" in card.get("status", ""), "T6 状态应为签到成功，实得 %r" % card.get("status"))


def test_site_offline():
    """接口拒绝 + 公告仍在 → 站点下线，退出 0（不是我们的失败）。"""
    fake = FakeAPI(
        [task_payload(finish=0), task_payload(finish=0)],
        mission_error=RuntimeError("签到 返回异常：HTTP 403"),
    )
    code, card, _ = run(fake, offline=True)
    check(code == 0, "T7 站点下线不该标红，实得退出码 %s" % code)
    check("站点已下线" in card.get("status", ""), "T7 状态应为站点已下线，实得 %r" % card.get("status"))


def test_real_failure():
    """接口拒绝 + 没有公告 → 真失败，必须退出非 0。"""
    fake = FakeAPI(
        [task_payload(finish=0), task_payload(finish=0)],
        mission_error=RuntimeError("签到 返回异常：HTTP 500"),
    )
    code, card, _ = run(fake, offline=False)
    check(code != 0, "T8 真失败必须退出非 0，实得 %s" % code)
    check("未生效" in card.get("status", ""), "T8 状态应为未生效，实得 %r" % card.get("status"))


def test_auth_rejected():
    """403 请先登录 → 明确提示，不甩 traceback。"""
    fake = FakeAPI([], auth_fail=True)
    code, card, _ = run(fake)
    check(code != 0, "T9 登录态被拒应退出非 0，实得 %s" % code)
    check("登录态" in card.get("status", ""), "T9 状态应为登录态不被接受，实得 %r" % card.get("status"))
    check("请先登录" in card.get("note", ""), "T9 备注要带上服务端原话，实得 %r" % card.get("note"))


def test_no_mission_item():
    fake = FakeAPI([{"task": {"task_post": {"name": "发布文章", "finish": 0, "times": 1}}}])
    code, card, _ = run(fake)
    check(code != 0, "T11 找不到签到项应为失败，实得退出码 %s" % code)
    check("未找到签到项" in card.get("status", ""), "T11 状态应点名未找到，实得 %r" % card.get("status"))


# ───────────────────────── T10 卡片 ─────────────────────────


def test_card_content():
    fake = FakeAPI([task_payload(finish=1, times=1)])
    _, card, _ = run(fake, bot_id="https://example.invalid/bot")
    check(card.get("days") == 3, "T10 卡片应带连续天数，实得 %r" % card.get("days"))
    check(card.get("credit") == 12, "T10 卡片应带锋币，实得 %r" % card.get("credit"))
    check("发布文章" in card.get("progress", ""), "T10 卡片应带其它任务进度，实得 %r" % card.get("progress"))
    check("签到" not in card.get("progress", ""), "T10 其它任务里不该重复签到项")


def test_summary_failure_not_fatal():
    """概况接口挂了不影响结论 —— 同 52pojie 读吾爱币的原则。"""

    class SummaryBroken(FakeAPI):
        def __call__(self, session, action, label):
            if action == "getUserMission":
                self.calls.append(action)
                raise RuntimeError("读取签到概况 请求失败（网络问题）")
            return FakeAPI.__call__(self, session, action, label)

    fake = SummaryBroken([task_payload(finish=1, times=1)])
    code, card, _ = run(fake)
    check(code == 0, "T12 概况读不到不该把已签到判成失败，实得 %s" % code)
    check("今日已签到" in card.get("status", ""), "T12 状态应保持已签到")


# ───────────────────────── 调度 ─────────────────────────


def main():
    tests = [
        test_token_normalize,
        test_as_int,
        test_find_mission,
        test_already_signed,
        test_sign_success,
        test_mission_error_but_finish_grew,
        test_site_offline,
        test_real_failure,
        test_auth_rejected,
        test_no_mission_item,
        test_card_content,
        test_summary_failure_not_fatal,
    ]
    for test in tests:
        before = len(fails)
        test()
        print("%s %s" % ("PASS" if len(fails) == before else "FAIL", test.__name__))

    if fails:
        print("\n发现 %d 处问题：" % len(fails))
        for item in fails:
            print("  - %s" % item)
        sys.exit(1)

    print("\n全部通过（%d 组）" % len(tests))


if __name__ == "__main__":
    main()
