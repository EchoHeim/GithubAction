#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""致美化（zhutix.com）每日签到 —— 复用 B2 主题登录态，纯 HTTP，不开浏览器。

━━━ 接口是怎么找出来的（2026-11-26 实测）━━━
致美化是 WordPress + B2 主题。任务中心的签到按钮不在页面表单里，前端
`Assets/fontend/task.js` 直接打 B2 自己的 REST 接口：

    POST https://zhutix.com/wp-json/b2/v1/getTaskData   # 读任务列表（签到项的 finish/times）
    POST https://zhutix.com/wp-json/b2/v1/userMission   # 执行签到，无 body
    POST https://zhutix.com/wp-json/b2/v1/getUserMission # 连续天数 / 锋币（顺带读，非必需）

认证只有一条路，`Assets/fontend/main.js` 里写死：

    const b2token = b2getCookie('b2_token')
    tp.defaults.headers.common['Authorization'] = 'Bearer ' + b2token

也就是**把 cookie 里的 b2_token 当 JWT 塞进 Authorization 头**。不需要 WP nonce，
不需要浏览器指纹，不需要过验证码 —— 所以这段 cookie 一贴，纯 requests 就能跑完。

无 token 或 token 失效时，接口原话都是同一句（实测）：

    {"code":"task_error","message":"请先登录","data":{"status":403}}

⚠️ 这也意味着**没法区分「没给 token」和「token 过期」** —— 两者都是请先登录。
   卡片里因此只说「登录态不被接受」，不去猜是哪种。

━━━ 站点现状（重要，别把公告当成 bug）━━━
/task/ 页面挂着一行橙色公告：

    「签到和关注功能占用资源过大导致网站经常卡死，暂时下线，等待完善；
      临时补偿方案：评论任务提升到6次。」

也就是说站点**自己**随时可能把签到停掉。脚本把这种情况单独认成
「站点已下线签到」（退出码 0）—— 那不是签到失败，天天报红只会让人对告警麻木。
判据是**两个同时成立**：签到接口拒绝 + /task/ 页面上那行公告还在。
只靠公告是不够的：公告挂着但功能照样能用的站点太多了。

━━━ 判定原则 ━━━
「接口返回 200」不算签到成功。唯一算数的是**回查任务列表里签到项的 finish 涨了**。
task.js 里的前端也一样：它只是乐观地把 finish 写死为 1，并没有真的读回服务端。

用法：
    ZHUTIX_COOKIE="b2_token=eyJ...; wordpress_logged_in_xxx=..." python -m Selenium.CheckIN.zhutix
    ZHUTIX_COOKIE="eyJ..." python -m Selenium.CheckIN.zhutix    # 只贴 token 值也行

环境变量：
    ZHUTIX_COOKIE   整行 cookie，或只贴 b2_token 的值（JWT）。唯一必需项。
    FEISHU_BOT_ID   飞书机器人 webhook，给了才推卡片。

退出码：0 = 已签到 / 签到成功 / 站点已下线签到；非 0 = 登录态失效或接口异常。
"""

import json
import os
import re
import sys
import time

import requests

from Messaging.Feishu import Feishu_SendCardMsg

# 输出被重定向到文件或管道时默认是块缓冲，日志会滞后甚至乱序（同 run_local.py）
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

BASE = "https://zhutix.com"
REST = BASE + "/wp-json/b2/v1/"
TASK_PAGE = BASE + "/task/"

COOKIE_ENV = "ZHUTIX_COOKIE"
DEBUG_DIR = os.path.join(os.getcwd(), "zhutix-debug")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# cookie 行里的 b2_token。值里不会有分号，所以 [^;]+ 够了。
_COOKIE_TOKEN_RE = re.compile(r"(?:^|;\s*)b2_token=([^;]+)")

# 站点公告原文：签到和关注功能占用资源过大导致网站经常卡死，暂时下线，等待完善
_OFFLINE_RE = re.compile(r"签到和关注功能[^<]{0,80}?下线")


class AuthError(RuntimeError):
    """登录态不被接受。单独一类，因为要用户做的事和网络错误完全不同。"""


def normalize_token(raw):
    """从用户贴进来的东西里取出 b2_token，返回 (token, 来源说明)。

    三种贴法都认：
      - 整行 cookie `b2_token=eyJ...; wordpress_logged_in_...=...` → 正则抠出来；
      - 裸 JWT        `eyJhbGciOi....eyJkYXRh....签名`             → 原样用；
      - 贴了 cookie 但里面没有 b2_token                            → 返回空 + 点名有哪些。
    """
    raw = (raw or "").strip().strip(";").strip()
    if not raw:
        return "", "空"

    matched = _COOKIE_TOKEN_RE.search(raw)
    if matched:
        return matched.group(1).strip(), "cookie 行"

    if ";" in raw or "=" in raw.split(".")[0][:24]:
        # 看着像 cookie 行却没有 b2_token —— 常见是把别的站点的 cookie 贴过来了
        names = [part.split("=", 1)[0].strip() for part in raw.split(";") if "=" in part]
        return "", "cookie 行里没有 b2_token（只有 %s）" % (", ".join(names[:8]) or "无键名")

    return raw, "裸 token"


def make_session(token):
    """建带登录态的会话。头照抄浏览器里 axios 的默认值。"""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": TASK_PAGE,
            "Authorization": "Bearer " + token,
        }
    )
    return session


def _dump(name, data):
    """原始响应落盘。接口结构一变，靠它自证，不用猜。"""
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        path = os.path.join(DEBUG_DIR, "%s_%s.json" % (name, time.strftime("%H%M%S")))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        return path
    except (OSError, TypeError, ValueError) as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (name, err))
        return ""


def call_api(session, action, label):
    """打一个 B2 接口，返回解析后的 JSON。失败就地定性。"""
    url = REST + action
    try:
        # B2 前端是 axios.post(url) 无 body；这里给个空对象，语义等价且不会踩 WAF 的空包规则
        resp = session.post(url, json={}, timeout=25)
    except requests.RequestException as err:
        raise RuntimeError("%s 请求失败（网络问题，不是凭据问题）: %s" % (label, err))

    text = resp.text or ""
    try:
        body = resp.json()
    except ValueError:
        _dump("bad_json_%s" % action, {"status": resp.status_code, "text": text[:2000]})
        raise RuntimeError(
            "%s 返回的不是 JSON（HTTP %s）: %s —— 多半是被 CDN/WAF 拦了，"
            "换个出口 IP 或在日志里看完整响应" % (label, resp.status_code, text[:160])
        )

    message = str(body.get("message", "")) if isinstance(body, dict) else ""

    if resp.status_code == 403 or "请先登录" in message:
        raise AuthError(
            "%s 拒绝：%s（HTTP %s）。站点不区分「没给 token」和「token 过期」，"
            "两种可能都成立 —— 先确认 b2_token 贴全了，再考虑重新登录抄一遍"
            % (label, message or "请先登录", resp.status_code)
        )

    if resp.status_code >= 400:
        _dump("api_error_%s" % action, body)
        # 极少见但真会发生：WAF 用 4xx 回一段 json 数组/字符串，直接 .get 会 AttributeError
        detail = body if isinstance(body, dict) else {"raw": body}
        raise RuntimeError(
            "%s 返回异常：HTTP %s code=%s message=%s"
            % (label, resp.status_code, detail.get("code"), message or "无")
        )

    return body


def as_int(value, default=0):
    """接口里 finish/times 可能给字符串，统一转 int。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def find_mission(data):
    """从 getTaskData 里挑出签到项，返回 (key, item)。

    结构（task.js 的 v-for 可证）：task 是个 dict，key → 任务对象，
    每项有 name/icon/finish/times/credit/url。签到项的 key 惯用 task_mission，
    但站点换过 key 也说不定 —— 所以先按 name 里有没有「签到」找，再退回 key。
    """
    tasks = data.get("task") if isinstance(data, dict) else None
    if not isinstance(tasks, dict):
        return None, None

    for key, item in tasks.items():
        if isinstance(item, dict) and "签到" in str(item.get("name", "")):
            return key, item

    item = tasks.get("task_mission")
    if isinstance(item, dict):
        return "task_mission", item
    return None, None


def describe_tasks(data, skip_key=None):
    """把今日任务拼成一行进度，给卡片当血肉。签到项自己会单独说，这里跳过。"""
    tasks = data.get("task") if isinstance(data, dict) else None
    if not isinstance(tasks, dict):
        return ""
    parts = []
    for key, item in tasks.items():
        if key == skip_key or not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        parts.append("%s %s/%s" % (name, as_int(item.get("finish")), as_int(item.get("times"), 1)))
    return " ｜ ".join(parts)


def read_summary(session):
    """读连续签到天数 / 锋币。**非必需** —— 读不到不该拖垮签到本身。

    实测响应（未登录时）：
        {"mission":{"date":"","credit":0,"always":0,
                    "tk":{"days":0,"credit":0,"bs":"3"},"my_credit":0,"current_user":0}}
    字段含义按 B2 惯例推：tk.days 连续天数、my_credit 我的锋币、current_user 用户 ID。
    """
    body = call_api(session, "getUserMission", "读取签到概况")
    mission = body.get("mission") if isinstance(body, dict) else None
    if not isinstance(mission, dict):
        return {}
    tk = mission.get("tk") if isinstance(mission.get("tk"), dict) else {}
    return {
        "credit": mission.get("my_credit"),
        "days": tk.get("days"),
        "user": mission.get("current_user"),
    }


def site_offline(session):
    """检查 /task/ 页面上那行「签到…下线」公告还在不在。

    只在签到被拒之后才调用 —— 公告挂着但功能照常的站点太多，
    拿公告单独当判据会把「真失败」误判成「站点下线」，那是最坏的一种错。
    """
    try:
        resp = session.get(TASK_PAGE, timeout=25)
    except requests.RequestException as err:
        print("[WARN] 读取任务页失败: %s" % err)
        return False

    if resp.status_code != 200:
        print("[WARN] 任务页返回 HTTP %s，不据此判断站点状态" % resp.status_code)
        return False

    hit = _OFFLINE_RE.search(resp.text or "")
    if hit:
        print("===> 任务页公告命中: %s" % hit.group(0).strip())
        return True
    return False


def notify(bot_id, status, days="", credit="", progress="", note=""):
    """推飞书卡片。推送失败只告警，绝不因此改签到结论。"""
    if not bot_id:
        # 显式说出来。静默不推最容易被当成「配了但没收到」，
        # 排查时又要从头翻 workflow 的 env —— 一行日志省半小时。
        print("[WARN] 没配 FEISHU_BOT_ID，跳过飞书推送（签到结论不受影响）")
        return

    content = ["**签到状态**: %s" % status]
    if days not in ("", None):
        content.append("**连续签到**: %s 天" % days)
    if credit not in ("", None):
        content.append("**锋币余额**: %s" % credit)
    if progress:
        content.append("**今日其它任务**: %s" % progress)
    if note:
        content.append("**备注**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        sent = Feishu_SendCardMsg(bot_id, " 致美化 签到 ", "\n".join(content))
        print("===> 飞书卡片已推送" if sent else "===> [WARN] 飞书卡片没发出去，原因见上一行")
    except Exception as err:
        print("[WARN] 飞书推送异常（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """凭据只走环境变量：cookie 动辄几百字符，命令行参数容易被截断/转义吃掉。"""
    return {
        "cookie": os.getenv(COOKIE_ENV) or "",
        "bot_id": os.getenv("FEISHU_BOT_ID") or (argv[1] if len(argv) > 1 else ""),
    }


def zhutix(cookie="", bot_id=""):
    token, how = normalize_token(cookie)
    print("===> 凭据检查: token=%d字（%s）/ FEISHU_BOT_ID=%d字" % (len(token), how, len(bot_id or "")))
    if not token:
        sys.exit(
            "[X] 没有可用的 b2_token（%s）。\n"
            "    取法：浏览器登录 %s\n"
            "          F12 → Application → Storage → Cookies → https://zhutix.com\n"
            "          找到 b2_token，复制 Value（整行 cookie 也行），填进 GitHub Secret %s\n"
            "    ⚠️ b2_token 是 JWT，长度 200+ 字符，别只抄前半截。"
            % (how, TASK_PAGE, COOKIE_ENV)
        )

    session = make_session(token)
    status = "签到失败"
    note = ""
    days = credit = progress = ""
    ok = False  # 只有拿到「finish 涨了」才翻成 True，别的都算没过

    try:
        data = call_api(session, "getTaskData", "读取任务列表")
        key, item = find_mission(data)
        if item is None:
            _dump("taskdata_no_mission", data)
            status = "未找到签到项"
            note = "任务列表里没有名字带「签到」的任务，站点可能改了任务结构，原始响应已落盘 zhutix-debug/"
            print("[WARN] %s" % note)
        else:
            progress = describe_tasks(data, skip_key=key)
            finish = as_int(item.get("finish"))
            times = as_int(item.get("times"), 1) or 1
            print("===> 签到项 %s: %d/%d（奖励 %s）" % (key, finish, times, item.get("credit")))
            if progress:
                print("===> 今日其它任务: %s" % progress)

            if finish >= times:
                status = "今日已签到（%d/%d）" % (finish, times)
                ok = True
                print("===> 已经签过了，不再重复调用")
            else:
                print("===> 调 userMission 签到")
                try:
                    _dump("userMission_ok", call_api(session, "userMission", "签到"))
                except AuthError:
                    raise
                except RuntimeError as err:
                    # 接口报错也可能只是「今天签过了」。B2 的文案不固定，不猜 ——
                    # 一律靠下面那次回查定性，这里只留痕。
                    print("[WARN] 签到调用报错，等回查定论: %s" % err)

                # ⚠️ 唯一的成功判据：回查 finish 涨没涨。接口返回 200 不算数。
                time.sleep(1.5)
                after = call_api(session, "getTaskData", "回查任务列表")
                _, item2 = find_mission(after)
                finish2 = as_int(item2.get("finish")) if item2 else finish
                times2 = (as_int(item2.get("times"), 1) or 1) if item2 else times
                print("===> 回查签到项: %d/%d" % (finish2, times2))

                if finish2 > finish or finish2 >= times2:
                    status = "签到成功（%d/%d）" % (finish2, times2)
                    ok = True
                elif site_offline(session):
                    # 站点自己关的功能。如实说，退出码 0 —— 天天红叉只会让人对告警麻木。
                    status = "站点已下线签到"
                    note = "接口拒绝了签到，且 /task/ 页面仍挂着「签到和关注功能…暂时下线」的公告 —— 不是脚本的问题"
                    ok = True
                    print("[WARN] %s" % note)
                else:
                    status = "签到未生效（仍 %d/%d）" % (finish2, times2)

        try:
            summary = read_summary(session)
            days = summary.get("days", "")
            credit = summary.get("credit", "")
            if days not in ("", None):
                print("===> 连续签到: %s 天" % days)
            if credit not in ("", None):
                print("===> 锋币余额: %s" % credit)
        except Exception as err:
            # 概况接口挂了不影响结论，同 52pojie 读吾爱币的原则
            print("[WARN] 签到概况读取失败（不影响结论）: %s" % err)

        print("===> 签到结果: %s" % status)
    except AuthError as err:
        # 登录态问题不抛栈 —— CI 日志里要的是一句能照着做的提示，不是 traceback
        status = "登录态不被接受"
        note = str(err)[:200]
        print("[X] %s" % note)
    except Exception as err:
        status = "签到失败"
        note = str(err)[:200]
        raise
    finally:
        # 无条件调用：没配机器人时由 notify 自己喊一声，别让「静默不推」看起来像「推了没收到」
        notify(bot_id, status, days, credit, progress, note)

    if not ok:
        sys.exit("[X] 签到没通过：%s" % status)


if __name__ == "__main__":
    if len(sys.argv) == 1 and not os.getenv(COOKIE_ENV):
        sys.exit(
            "用法: python -m Selenium.CheckIN.zhutix\n"
            "  凭据只走环境变量 %s（取法见 LOCAL_RUN.md）\n"
            "  可选: python -m ... <飞书机器人 webhook>" % COOKIE_ENV
        )
    zhutix(**resolve_credentials(sys.argv))
