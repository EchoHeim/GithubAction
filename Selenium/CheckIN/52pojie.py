# -*- coding: UTF-8 -*-
"""52pojie（吾爱破解）签到：Cookie 复用登录态 + 过 WAF + 领每日签到任务。

站点是 Discuz，签到挂在「任务中心」的每日签到任务上（`home.php?mod=task&do=apply&id=2`）。

━━━ 第一层：任务页被站点自家 wzws WAF 保护 ━━━
直接访问会跳到 `waf_text_verify.html` —— 一张「请完成安全验证」的**图片验证码**页
（4 位小写字母 + 干扰线）。curl 拿不到任何有用内容，**必须在真浏览器里过验证码**，
否则后面全是 5KB 的验证页，看起来像「选择器失效」，实际是压根没进去。
`pass_waf()` 负责过这一关：元素级截图取验证码图 → ddddocr 识别 → 提交 → 直到跳出验证页。
实测（2026-09-26 本机直连）beta 模型一次识别正确（'epps'），默认模型把 4 位读成 3 位
（'ees'）——所以两模型一致时直接采信，不一致时优先字符更多的那个。
验证失败只换一张新图，**不计入登录失败次数**，可以放心多轮重试。

━━━ 第二层：登录页有人机验证，密码登录在自动化里走不通 ━━━
2026-09-26 CI 实测：三次「登录超时」、日志里一个字都没有。本机复现 + 取证后定性：
  - 登录页（member.php?mod=logging&action=login）的验证码是 **Cloudflare Turnstile**，
    外面套着站点自己的「点击验证」外壳（`#grbg_xx` / `#grcontainer_xx` / `.cf-turnstile`）；
  - 它是服务端按客户端风险**按需注入**的（静态页里没有这段），Discuz 通过
    `misc.php?mod=seccode&action=update` 把验证行塞进表单；
  - 在本机（东莞家宽、无头与有头都试过）`challenges.cloudflare.com` 的 api.js 与
    challenge-platform 脚本**全部加载失败**（performance: status=0 size=0），
    widget 连 iframe 都建不出来，`cf-turnstile-response` 恒为空；
  - 不带 token 提交，服务端直接回「抱歉，验证码填写错误」。
  **这不是选择器问题，改代码没用。**（2026-09-28 又补量了一次：域名能解析，但
  `challenges.cloudflare.com:443` 直接连接超时 —— 是**线路到不了**，跟"像不像人"无关。）

━━━ 所以本脚本只走 Cookie（2026-09-28 定稿）━━━
密码登录路径已整体移除，只保留 **Cookie 复用登录态**（`PJ52_COOKIE`）——
这是 52pojie 这类站点的通行做法：登录不可自动化，但登录态可以复用。
（CI 上还额外验证过一次：同一份 Cookie 家宽 IP 有效、美国机房 IP 失效，会话与环境相关。）

用法：
    PJ52_COOKIE="htVC_2132_saltkey=...; htVC_2132_auth=...; htVC_2132_sid=..." \
        python -m Selenium.CheckIN.52pojie

可选环境变量：
    PJ52_COOKIE         登录态 Cookie，形如 `name=value; name2=value2`（唯一必需项）
    FEISHU_BOT_ID       飞书机器人 webhook，给了才推卡片
                        （卡片含签到状态 + 当前积分 + 吾爱币 + 回帖结果）
    PJ52_TASK_URL       签到任务地址，默认 home.php?mod=task&do=apply&id=2
    PJ52_DRAW_URL       任务奖励领取地址，默认 home.php?mod=task&do=draw&id=2
    PJ52_CREDIT_URL     「我的积分」页，读吾爱币用，默认 home.php?mod=spacecp&ac=credit
    PJ52_WAF_ROUNDS     单次过 WAF 的验证码重试上限，默认 8
    PJ52_WAF_ATTEMPTS   过完验证码又被拦回来的重试次数，默认 3
    PJ52_FORUM_URL      回帖板块，默认 forum-16-1.html（『精品软件区』）
    PJ52_REPLY          置 0 关掉回帖（只签到），默认开

    PJ52_REPLY_TEXT     回帖内容，默认「谢谢分享，正好需要这个工具，感谢楼主~」
                        （别填太短：站点有最小字数限制，见 REPLY_TEXT 处的说明）

    PJ52_REPLY_STRICT   置 0 则回帖失败不影响整体退出码，默认 1（失败即红）

⚠️ 回帖是「跑一次发一条」：本机/CI 手动多跑几次就会多发几条。吾爱版规明写
「禁止复制他人回复等『恶意灌水』行为，违者重罚」，别把它当刷帖脚本用。

签到结果按站点真实回执判定（`#messagetext`）：申请成功 / 今日已申请 / 需补领奖励。
任何无法归类的回执都 dump 现场后抛错，绝不再出现「打了日志就算成功」。
失败现场写进 52pojie-debug/，CI 里由 workflow 收集成 artifact。

━━━ 回帖判定的坑（2026-09-28）━━━
CI 上回帖报「回帖被拒（抱歉，您）」，罪魁不是站点、是**自己把话截断了**：
错误短语表里「抱歉，您」排在第一位，命中即返回，于是所有「抱歉，您xxx」的
真实原因（字数不够 / 间隔太短 / 权限不足 / 内容要审核）全被砍成 3 个字，
连 artifact 里的现场快照都看不出服务端到底说了什么。修法见 classify_reply_blob：
  - 命中多个短语时取**最长**的那条，并把**整句话**带进日志与异常；
  - 判定前先采一次**提交前基线**做差分，页面固有文本不算「本次错误」；
  - 审核类回执从「错误」里挪出来，算「已提交待审核」——那其实是发出去了。

"""

import json
import os
import random
import re
import socket
import sys
import time

from Selenium.base import *
from Messaging.Feishu import Feishu_SendCardMsg

HOME_URL = os.getenv("PJ52_HOME_URL", "https://www.52pojie.cn/")
TASK_URL = os.getenv(
    "PJ52_TASK_URL",
    "https://www.52pojie.cn/home.php?mod=task&do=apply&id=2&referer=%2F",
)
DRAW_URL = os.getenv(
    "PJ52_DRAW_URL", "https://www.52pojie.cn/home.php?mod=task&do=draw&id=2"
)
# 设置 → 积分页：吾爱币数量只在这里看得到（页头那个「积分」是总积分，两者不同）
CREDIT_URL = os.getenv(
    "PJ52_CREDIT_URL", "https://www.52pojie.cn/home.php?mod=spacecp&ac=credit"
)
# 回帖得积分的目标板块，默认『精品软件区』（fid=16）
FORUM_URL = os.getenv("PJ52_FORUM_URL", "https://www.52pojie.cn/forum-16-1.html")
# 回帖内容与开关。回复本身是「每日互动」，跑一次发一条 —— 不想发就把 PJ52_REPLY 设成 0

# ⚠️ 别往短了改：Discuz 有「帖子小于 N 个字符」的最小字数限制（站点侧设置）。
#    早先默认的「谢谢分享~」只有 6 个字符，很可能正是被这条挡下的（2026-09-28）。
REPLY_TEXT = os.getenv("PJ52_REPLY_TEXT", "谢谢分享，正好需要这个工具，感谢楼主~")

REPLY_ENABLE = os.getenv("PJ52_REPLY", "1") != "0"
# 回帖失败是否判定整次运行失败。默认失败（宁可红也不要静默），只签到就把它顺手关掉
REPLY_STRICT = os.getenv("PJ52_REPLY_STRICT", "1") != "0"

WAF_ROUNDS = int(os.getenv("PJ52_WAF_ROUNDS", "8"))
# 过完验证码又被拦回 WAF 页时，最多重来几次（见 open_task）
WAF_ATTEMPTS = int(os.getenv("PJ52_WAF_ATTEMPTS", "3"))

DEBUG_DIR = os.path.join(os.getcwd(), "52pojie-debug")
# 必须在任何写文件之前建好：base.py 写验证码图用的是裸 open()，不会替你建父目录
os.makedirs(DEBUG_DIR, exist_ok=True)

# WAF 验证页的指纹。三个都是页面独有特征，正常页面上不会出现
WAF_MARKERS = ("waf_text_captcha", "waf_text_verify", "请完成安全验证")

# Cookie 模式（推荐）：从浏览器里把登录后的 Cookie 抄过来，跳过登录页与人机验证。
# 这是 52pojie 这类站点的通行做法 —— 登录本身不可自动化，但**登录态 Cookie 可以复用**。
PJ52_COOKIE_ENV = "PJ52_COOKIE"
COOKIE_DOMAIN = ".52pojie.cn"

# Discuz 认登录态必需的两项（都是 HttpOnly，只能从真请求头里取，见 check_cookie_completeness）
AUTH_COOKIE_SUFFIX = "_auth"
SALTKEY_COOKIE_SUFFIX = "_saltkey"

# 签到回执的语义分类。Discuz 任务页的文案集中在 #messagetext
TASK_DONE_MARKERS = (
    "申请任务成功",
    "任务申请成功",
    "签到成功",
    "恭喜",
    "已完成，请领取奖励",
)
TASK_ALREADY_MARKERS = (
    "已经申请过",
    # ⚠️ 2026-09-27 同日重复跑实测到的原文：
    #    「抱歉，本期您已申请过此任务，请下期再来」
    # 注意是「已申请过」不是「已经申请过」——只写带「经」的那版会漏掉，被判成 unknown 抛错。
    "已申请过",
    "请下期再来",
    "已完成过",
    "已经完成",
    "只能申请一次",
    "已经签到",
    "已签到",
    "周期内",
)
TASK_DRAW_MARKERS = ("领取奖励", "领取任务奖励", "去领取", "请领取")
TASK_NOT_LOGIN_MARKERS = ("需要先登录", "请先登录", "登录后才能")

# ── 回帖（快捷回复）相关 ──
# 板块列表里普通帖在 <tbody id="normalthread_<tid>"> 内，置顶帖是 stickthread_ —— 只用前者，
# 免得把公告/置顶帖也回了。
THREAD_LINK_XPATHS = ("//tbody[starts-with(@id,'normalthread_')]//a[@class='s xst']",)
REPLY_BOX_XPATHS = ("//*[@id='fastpostmessage']",)
REPLY_SUBMIT_XPATHS = (
    "//*[@id='fastpostsubmit']",
    "//button[contains(@id,'fastpostsubmit')]",
)
# Discuz 的快捷回复是 ajax 提交，结果以 <script> 形式注入（本主题注入到 <head>）
REPLY_RETURN_ID = "fastpostreturn"
# 成功的权威标志：服务端返回的 succeedhandle_fastpost(...) 脚本。
# ⚠️ 这套主题里**没有定义** succeedhandle_fastpost，所以它不会跳转、页面也无变化 ——
# 只有这行脚本文本能证明「发出去了」（2026-09-27 用 CDP 抓到响应体才确认这一点）。
REPLY_SUCCESS_MARKERS = (
    "succeedhandle_fastpost",
    "回复发布成功",
    "回复成功",
    "发表回复成功",
)

# 只挑「一定是错误」的短语，别把版规提示里的「灌水」之类当失败信号。
# ⚠️ 判定时不看「谁先命中」，而是取**命中里最长的那个**（见 classify_reply_blob）：
#    泛短语只当兜底，越具体的越优先 —— 否则「抱歉，您两次发表间隔少于 15 秒」
#    会被「抱歉，您」吃掉，日志里只剩 3 个字（2026-09-28 踩过）。

REPLY_ERROR_MARKERS = (
    "抱歉，您",
    "没有权限",
    "无权",
    "两次发表间隔",
    "间隔小于",
    "请填写验证码",
    "验证码错误",
    "被禁止",
    "已被禁用",
    "未定义操作",
    # 下面这些是 2026-09-28 补的：Discuz 侧的真实拦截文案，都不含歧义
    "帖子小于",
    "不良信息",
    "包含非法",
    "绑定手机",
    "所在的用户组",
    "无法发表",
    "不能发表",
    "禁止发表",
    "已被关闭",
    "重复回复",
    "已经回复过",
    "权限不足",
)
# 「等审核」不是失败 —— 回复已经提交成功，只是要人工过一遍。
# 从错误表里挪出来单独归类，免得把发出去的回复报成失败。
REPLY_PENDING_MARKERS = (
    "需要审核",
    "待审核",
    "审核后",
    "审核通过",
)
# 回复验证码（Discuz seccode）：出现才填 —— 元素级截图喂 ddddocr
POST_CAPTCHA_INPUT_XPATHS = (
    "//input[starts-with(@id,'seccodeverify')]",
    "//input[@name='seccodeverify']",
)
POST_CAPTCHA_IMG_XPATHS = (
    "//*[starts-with(@id,'seccode_')]//img",
    "//img[contains(@src,'mod=seccode')]",
    "//*[contains(@class,'seccodeimg')]",
)


def _safe_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)
    except OSError as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (path, err))


def dump_debug(driver, tag, notes=(), secrets=()):
    """留存失败现场：URL、提示文案、DOM、截图。

    入库前先清空输入框、抹掉账号密码 —— 仓库是公开的，artifact 谁都能下。
    """
    prefix = os.path.join(DEBUG_DIR, "%s_%s" % (tag, time.strftime("%H%M%S")))

    info = []
    try:
        info.append("url: %s" % driver.current_url)
        info.append("title: %s" % driver.title)
    except WebDriverException as err:
        info.append("url/title 读取失败: %s" % err)
    info.extend("messagetext: %s" % t for t in get_page_texts(driver)[:6])
    info.extend("note: %s" % n for n in notes)

    try:
        driver.execute_script(
            "document.querySelectorAll('input').forEach(function(e){e.value='';});"
        )
    except WebDriverException:
        pass

    try:
        html = driver.page_source
    except WebDriverException as err:
        html = "page_source 读取失败: %s" % err
    text = "\n".join(info) + "\n"
    for secret in secrets:
        if secret:
            html = html.replace(secret, "***")
            text = text.replace(secret, "***")

    _safe_write(prefix + ".txt", text)
    _safe_write(prefix + ".html", html)
    try:
        _safe_write(prefix + ".png", driver.get_screenshot_as_png())
    except WebDriverException as err:
        print("[WARN] 现场截图失败: %s" % err)

    print("===> 失败现场已留存: %s.{txt,html,png}" % prefix)
    print(text.strip())


def get_page_texts(driver):
    """抓页面上的提示文案。

    Discuz 的提示分两种承载：任务/操作回执在 `#messagetext`，
    登录失败在 `#returnmessage_<hash>`。两个都收，诊断时最有用。

    ⚠️ 必须用 JS 读 `textContent`，**不能用 Selenium 的 `element.text`**：
    后者返回的是「渲染后的可见文本」，元素被 `display:none` 的浮层包着就返回空串。
    Discuz 的登录回执正好写在浮层层里（`#layer_login_xx > h3 > em#returnmessage_xx`），
    于是 2026-09-26 的 CI 上出现「明明服务端回了话，日志里却一个字都没有」——
    连着 3 次「既没看到登出链接，也没看到错误文案」，排查方向全被带偏。
    """
    try:
        return driver.execute_script("""
            var sel = ['#messagetext', "[id^='returnmessage_']",
                       '.alert_error', '.alert_info'];
            var out = [];
            sel.forEach(function(s){
              document.querySelectorAll(s).forEach(function(e){
                var t = (e.textContent || '').replace(/\\s+/g, ' ').trim();
                if (t && out.indexOf(t) < 0) out.push(t.slice(0, 200));
              });
            });
            return out.slice(0, 10);
            """) or []
    except WebDriverException:
        return []


def check_cookie_completeness(pairs):
    """检查 Cookie 里有没有 Discuz 认登录态必需的两项，返回缺失项列表。

    ⚠️ 这两个都是 **HttpOnly**：
      - `*_auth`    —— 登录态本体（uid + 密码哈希），没它等于没登录
      - `*_saltkey` —— 会话盐值
    `document.cookie` / Console 里**永远看不到它们**（实测：2026-09-27 lodge 用
    document.cookie 抄出来 21 项，auth 与 saltkey 全都不在）。所以缺项时的正确动作
    是从真请求头里取，脚本在这里点明，别让人以为是抄漏了。
    """
    names = [name for name, _ in pairs]
    missing = [
        suffix
        for suffix in (AUTH_COOKIE_SUFFIX, SALTKEY_COOKIE_SUFFIX)
        if not any(name.endswith(suffix) for name in names)
    ]
    if missing:
        print(
            "[WARN] Cookie 里缺 %s —— 多半是从 Console 的 document.cookie 抄的："
            "这两项是 HttpOnly，JS 读不到。\n"
            "       正确取法：F12 → Network → 刷新 → 点 Document 请求 → Request Headers 里的"
            " cookie 行（或右键请求 → Copy as cURL），那份一定包含它们。"
            % " / ".join("*" + name for name in missing)
        )
    return missing


def _document_time_origin(driver):
    """当前文档的 performance.timeOrigin —— 每次导航都会变，用它判断「新文档提交了没」。

    ⚠️ 为什么不能只看固定 sleep：`get_web_driver()` 设了
    `page_load_strategy="none"`，`driver.get()` 立刻返回，此刻 DOM 很可能还是**上一页**。
    2026-09-27 CI 上就踩了：`pass_waf()` 固定 sleep 1.5s 后读到的是首页（没有 WAF 标记）
    → 误判「已通过」，随后真用页面时发现停在 waf_text_verify.html（本机延迟小，没暴露）。
    """
    try:
        return driver.execute_script(
            "return (window.performance && performance.timeOrigin) || 0"
        )
    except WebDriverException:
        return 0


def wait_new_document(driver, previous_origin, timeout=25):
    """等新文档提交（timeOrigin 变化）。返回是否等到。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        origin = _document_time_origin(driver)
        if origin and origin != previous_origin:
            return True
        time.sleep(0.2)
    print("[WARN] 导航后 %ss 内没有新文档提交" % timeout)
    return False


def wait_document_ready(driver, timeout=15):
    """等 DOM 至少到 interactive（避免读到半成品页面）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if driver.execute_script("return document.readyState") != "loading":
                return True
        except WebDriverException:
            pass
        time.sleep(0.2)
    return False


def is_waf_page(driver):
    """当前是不是 WAF 的「请完成安全验证」页。"""
    try:
        if "waf_text_verify" in (driver.current_url or ""):
            return True
        source = driver.page_source or ""
    except WebDriverException:
        return False
    return any(marker in source for marker in WAF_MARKERS)


def is_logged_in(driver):
    """登录态判据：页面上出现登出链接。"""
    try:
        if "action=logout" in (driver.page_source or ""):
            return True
        return (
            find_visible(driver, ("//a[contains(@href,'action=logout')]",))[0]
            is not None
        )
    except WebDriverException:
        return False


def ocr_waf_captcha(png):
    """识别 WAF 图片验证码。

    实测（2026-09-26）4 位小写字母 + 干扰线，beta 模型一次报对、默认模型会漏字，
    所以策略是：两模型一致直接用；不一致时先信 beta（认识的字更全）。
    """
    normal = get_ocr(False).classification(png)
    beta = get_ocr(True).classification(png)
    print("===> WAF 验证码识别: 默认=%r beta=%r" % (normal, beta))

    normal = (normal or "").strip()
    beta = (beta or "").strip()
    if normal and normal.lower() == beta.lower():
        return normal
    if len(beta) >= len(normal):
        return beta or normal
    return normal


def pass_waf(driver, url, max_rounds=WAF_ROUNDS):
    """打开 url，必要时把 WAF 图片验证码过掉；返回是否拿到真实页面。

    验证码识别失败只是刷新一张新图，**不计入登录失败次数**，所以可以放心多轮重试。
    """
    # 先等新文档真的提交，再判断是不是 WAF 页 —— 否则会把上一页当成「已通过」
    origin = _document_time_origin(driver)
    driver.get(url)
    wait_new_document(driver, origin)
    wait_document_ready(driver)
    time.sleep(1.0)

    for round_no in range(1, max_rounds + 1):
        if not is_waf_page(driver):
            if round_no > 1:
                print("===> 第 %d 轮通过 WAF 验证" % round_no)
            return True

        element, _ = wait_visible(driver, ("//*[@id='Image1']",), 8, "WAF 验证码图")
        if element is None:
            print("[WARN] 在 WAF 页但找不到验证码图，按失败处理")
            return False

        try:
            png = element.screenshot_as_png
        except WebDriverException as err:
            print("[WARN] 截取 WAF 验证码失败: %s" % err)
            return False
        _safe_write(os.path.join(DEBUG_DIR, "waf_captcha_r%02d.png" % round_no), png)

        code = ocr_waf_captcha(png)
        if not code:
            print("===> WAF 验证码识别为空，换一张")
            click_waf_refresh(driver)
            continue

        box, _ = wait_visible(
            driver, ("//input[@name='captcha']",), 8, "WAF 验证码输入框"
        )
        if box is None:
            print("[WARN] 在 WAF 页但找不到验证码输入框，按失败处理")
            return False
        box.clear()
        box.send_keys(code)
        print("===> 第 %d/%d 轮提交 WAF 验证码: %r" % (round_no, max_rounds, code))

        submit, _ = find_visible(
            driver, ("//input[@type='submit']", "//button[@type='submit']")
        )
        if submit is None:
            return False
        submit.click()
        time.sleep(2.5)

        if not is_waf_page(driver):
            print("===> WAF 验证通过，当前: %s" % driver.current_url)
            return True
        click_waf_refresh(driver)

    print("[WARN] %d 轮都没过 WAF 验证码" % max_rounds)
    return False


def click_waf_refresh(driver):
    """点 WAF 页的刷新图标换一张验证码；找不到就整页重来。"""
    element, _ = find_visible(
        driver,
        (
            "//a[contains(@onclick,'changeImg')]",
            "//*[contains(@class,'refreshIcon')]",
        ),
    )
    if element is None:
        print("[WARN] 找不到验证码刷新按钮")
        return
    try:
        element.click()
        time.sleep(1.2)
    except WebDriverException as err:
        print("[WARN] 刷新验证码失败: %s" % err)


def classify_task(texts):
    """把任务回执归类。

    返回 success / already / need_draw / not_login / unknown 之一。
    Discuz 任务页的回执都在 #messagetext 里，文案变了就会落到 unknown —— 那时 dump 现场，
    不要猜。
    """
    joined = " ".join(texts)
    if not joined:
        return "unknown"
    if any(marker in joined for marker in TASK_NOT_LOGIN_MARKERS):
        return "not_login"
    if any(marker in joined for marker in TASK_ALREADY_MARKERS):
        return "already"
    if any(marker in joined for marker in TASK_DONE_MARKERS):
        # 「已完成，请领取奖励」这类要再走一次领取
        if any(marker in joined for marker in TASK_DRAW_MARKERS):
            return "need_draw"
        return "success"
    return "unknown"


def open_task(driver, url, label, secrets=()):
    """打开任务 URL、过 WAF、确认登录态，返回 (归类结果, 页面文案列表)。

    page_load_strategy="none" 下 get() 立即返回，所以每一步都等元素/URL 落地再判断，
    绝不靠宽泛选择器在错误页面上乱点。

    ⚠️ 过 WAF 要**循环确认**：站点在过完验证码、跳回目标页后有可能再挑战一次
    （referer 链 / IP 信誉），所以「pass_waf 返回 True」不等于「现在就在目标页」。
    """
    for attempt in range(1, WAF_ATTEMPTS + 1):
        if not pass_waf(driver, url):
            raise RuntimeError("%s：WAF 图片验证码未通过（%s）" % (label, url))
        # 等页面稳定下来再确认，避免拿半成品页面下结论。
        # ⚠️ 但不能久等：Discuz 的提示页会在 **3 秒后自动跳转**
        # （响应里带 setTimeout("location.href='home.php?mod=task&item=new'")），
        # 先 sleep 再读就会读到跳转后的任务列表页 —— 回执是空的（2026-09-27 踩过）。
        wait_document_ready(driver)
        time.sleep(0.2)
        if not is_waf_page(driver):
            break
        print("===> 过完验证码又被拦回 WAF 页（第 %d 次），重新过" % attempt)
    else:
        raise RuntimeError(
            "%s：连续 %d 次过完验证码又被拦回 WAF 页（%s）" % (label, WAF_ATTEMPTS, url)
        )

    # 等回执渲染出来：**高速轮询**（0.2s），因为提示页 3 秒后就会自动跳走。
    # ⚠️ 两条踩过的坑：
    #   1. 不要拿 is_logged_in() 当提前退出条件 —— 登出链接在页头，任何页面一进来就有，
    #      会让循环立刻退出、读到还没渲染的回执；
    #   2. 不要先 sleep 再读 —— 3 秒的跳转窗口一过，回执就随页面一起没了。
    deadline = time.time() + 15
    texts = []
    while time.time() < deadline:
        texts = get_page_texts(driver)
        if texts:
            break
        time.sleep(0.2)

    if not texts:
        # 可能是没赶上那个 3 秒窗口（页面已经跳去任务列表了）→ 重新打开一次再抓
        print("[WARN] 首轮没抓到回执，重新打开任务页再试一次")
        if pass_waf(driver, url):
            texts = []
            deadline = time.time() + 15
            while time.time() < deadline:
                texts = get_page_texts(driver)
                if texts:
                    break
                time.sleep(0.2)

    if not texts:
        # 读不到回执时把页面到底长什么样打进日志，别让人只看到一个「(空)」
        try:
            body = " ".join(
                (
                    driver.execute_script(
                        "return (document.body && document.body.textContent) || '';"
                    )
                    or ""
                ).split()
            )[:200]
            print("[WARN] 页面上没有任何回执元素，body 片段: %r" % body)
        except WebDriverException:
            pass

    for text in texts:
        print("===> %s 回执: %s" % (label, text))

    kind = classify_task(texts)
    if kind == "not_login" or (not is_logged_in(driver) and kind != "already"):
        dump_debug(
            driver,
            "%s_not_logged_in" % label,
            notes=[
                "%s 页看不到登出链接，session 可能没生效" % label,
                "url=%s" % driver.current_url,
                "是否 WAF 页: %s" % is_waf_page(driver),
            ],
            secrets=secrets,
        )
        raise RuntimeError("%s：页面不是登录态：url=%s" % (label, driver.current_url))
    return kind, texts


def sign_in(driver, secrets=()):
    """签到：申请每日签到任务 → 需要的话再领一次奖励。"""
    kind, texts = open_task(driver, TASK_URL, "签到任务", secrets)

    if kind == "already":
        return "今日已签到（跳过）"
    if kind == "success":
        return "签到成功"
    if kind == "unknown":
        dump_debug(
            driver,
            "task_unknown_reply",
            notes=["签到任务回执无法归类，原始文案见上"],
            secrets=secrets,
        )
        raise RuntimeError("签到任务回执无法识别：%s" % (" | ".join(texts) or "(空)"))

    # kind == "need_draw"：任务已完成但要单独领奖励
    draw_kind, draw_texts = open_task(driver, DRAW_URL, "奖励领取", secrets)
    if draw_kind in ("success", "already"):
        return "签到成功（奖励已领取）"
    dump_debug(
        driver,
        "draw_unknown_reply",
        notes=["奖励领取回执无法归类"],
        secrets=secrets,
    )
    raise RuntimeError("奖励领取回执无法识别：%s" % (" | ".join(draw_texts) or "(空)"))


def read_points(driver):
    """读头部导航里的「积分: NN」（`a#extcreditmenu`）。

    读不到就返回空串 —— 积分只是卡片上的锦上添花，不该拖垮签到本身。
    """
    try:
        text = (
            driver.execute_script(
                "var e = document.getElementById('extcreditmenu');"
                "return e ? (e.textContent || '') : '';"
            )
            or ""
        )
    except WebDriverException:
        return ""
    match = re.search(r"积分[:：]?\s*(\d+)", text)
    if match:
        return match.group(1)
    print("[WARN] 没在页头读到积分（原文本: %r）" % text.strip()[:40])
    return ""


# 吾爱币挂在设置 → 积分页（`home.php?mod=spacecp&ac=credit`）。
# ⚠️ 页头上的「积分: 57」是**总积分**（=发帖数×0.1 + 热心值×1.2 + 悬赏×1.5 + 贡献×1.5
#    + 威望×20 + 精华帖数×100 - 违规×20），跟吾爱币不是一回事，所以不能从页头推。
# 

# 页面里「我的积分」区块的标题形如 `吾爱币: 413 CB 帮助>`，数字在 <em> 里。
# 三层兜底，从最精确到最宽松：
#   1. 区块里 .credit_num 的纯数字；
#   2. 「吾爱币」后面的数字（取该节点之后最近的数字，兼容「标签—数值」分列的结构）；
#   3. 整页文本里 `吾爱币[:：]?\s*(\d[\d,]*)`。
# ⚠️ 顺序不能反：整页正则最容易误伤（右侧栏常同时挂着「贡献值 / 热心值 / 悬赏值」，
#    数值全是四位以内，一旦哪个标签文案变了就会串位 —— 掘金那边踩过同样的坑）。
CREDIT_SECTION_XPATHS = (
    "//*[@id='ct']",
    "//*[contains(@class,'credit')]",
)
CREDIT_EXTRACT_JS = r"""
    function pick(re) {
      return function(t) {
        if (!t) return '';
        var m = String(t).replace(/,/g, '').match(re);
        return m ? m[1] : '';
      };
    }
    var grabNum = pick(/(\d+)/);
    var grabCoin = pick(/吾爱币[:：]?\s*(\d[\d,]*)/);

    // 候选区块：设置页的主体区域
    var scopes = [];
    ['ct'].forEach(function(id){
      var e = document.getElementById(id);
      if (e) scopes.push(e);
    });
    document.querySelectorAll("[class*='credit']").forEach(function(e){ scopes.push(e); });
    if (!scopes.length) scopes.push(document.body);

    for (var i = 0; i < scopes.length; i++) {
      var scope = scopes[i];
      // 1) 精确类名：.credit_num / .credit_num_1（Discuz 老模板的「我的积分」数值格）
      var nums = scope.querySelectorAll(
        ".credit_num, [class^='credit_num'], [class*=' credit_num']");
      if (nums.length) {
        var first = grabNum(nums[0].textContent);
        if (first) return first;
      }
      // 2) 文本节点里带「吾爱币」的，取它后面最近的数字
      var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, null);
      var node;
      while ((node = walker.nextNode())) {
        var t = (node.textContent || '').trim();
        if (t.indexOf('吾爱币') < 0) continue;
        var inline = grabCoin(t);
        if (inline) return inline;
        // 标签和数字分列（本页就是这种）：顺着 DOM 往后找第一个纯数字节点
        var probe = node.parentNode;
        var hops = 0;
        while (probe && hops++ < 6) {
          var hit = probe.parentNode ? probe.parentNode : null;
          var found = '';
          if (hit) {
            hit.childNodes.forEach(function(c){
              if (found) return;
              if (c.nodeType === 3) {
                var v = grabNum(c.textContent);
                if (v) found = v;
              }
            });
          }
          if (found) return found;
          probe = probe.parentNode;
        }
      }
    }
    // 3) 整页兜底
    return grabCoin(document.body ? document.body.textContent : '') || '';
"""


def read_credits(driver, url=""):
    """读「我的积分」页里的**吾爱币**数量（截图上红框那行：`吾爱币: 413 CB`）。

    读不到就返回空串 —— 吾爱币只是卡片上的信息，绝不因此把签到判成失败。
    页面本身也会把真实结构写进失败现场（dump_debug），够排查。
    """
    url = url or CREDIT_URL
    if not pass_waf(driver, url):
        print("[WARN] 积分页 WAF 未通过，跳过吾爱币读取")
        return ""
    wait_document_ready(driver)
    time.sleep(1.0)

    try:
        value = (driver.execute_script(CREDIT_EXTRACT_JS) or "").strip()
    except WebDriverException as err:
        print("[WARN] 读取吾爱币失败: %s" % err)
        return ""
    if not value:
        print("[WARN] 没在积分页读到吾爱币（当前: %s）" % driver.current_url)
    return value


def pick_thread(driver, forum_url, secrets=()):
    """在板块列表第一页里随机挑一个普通帖，返回 (标题, 链接)。

    只取 `normalthread_*` 里的帖子 —— 置顶/公告是 `stickthread_*`，回那种帖没意义还容易踩版规。
    """
    if not pass_waf(driver, forum_url):
        raise RuntimeError("板块列表：WAF 图片验证码未通过（%s）" % forum_url)
    wait_document_ready(driver)
    time.sleep(1.5)

    links = []
    for xpath in THREAD_LINK_XPATHS:
        deadline = time.time() + 15
        while time.time() < deadline:
            links = driver.find_elements(By.XPATH, xpath)
            if links:
                break
            time.sleep(0.5)
        if links:
            break
    if not links:
        dump_debug(
            driver,
            "forum_no_thread",
            notes=["板块列表没找到普通帖链接（选择器或页面结构可能变了）"],
            secrets=secrets,
        )
        raise RuntimeError("板块列表未找到普通帖：%s" % driver.current_url)

    candidates = []
    for link in links:
        try:
            href = link.get_attribute("href") or ""
            title = " ".join((link.text or "").split())
        except WebDriverException:
            continue
        if re.search(r"/thread-\d+-\d+-\d+\.html", href) and title:
            candidates.append((title, href))
    if not candidates:
        dump_debug(
            driver,
            "forum_no_candidate",
            notes=["普通帖链接里没有可用的 thread-xxx 地址"],
            secrets=secrets,
        )
        raise RuntimeError("板块列表里没有可用的帖子链接")

    title, href = random.choice(candidates)
    print("===> 随机挑中 %d 个帖子中的: %r (%s)" % (len(candidates), title[:40], href))
    return title, href


def fill_post_captcha(driver):
    """回复验证码（Discuz seccode）：出现才填，元素级截图喂 ddddocr。

    没出现就什么都不做（多数情况下不出现）。识别结果交给服务端判定，
    失败会在回执里体现为「验证码」相关错误文案。
    """
    box, _ = find_visible(driver, POST_CAPTCHA_INPUT_XPATHS)
    if box is None:
        return False

    print("===> 回帖需要验证码，尝试 OCR")
    element, _ = find_visible(driver, POST_CAPTCHA_IMG_XPATHS)
    if element is None:
        print("[WARN] 找到验证码输入框但找不到验证码图")
        return False
    try:
        png = element.screenshot_as_png
    except WebDriverException as err:
        print("[WARN] 截取回帖验证码失败: %s" % err)
        return False
    _safe_write(os.path.join(DEBUG_DIR, "post_captcha.png"), png)

    code = ocr_waf_captcha(png)
    if not code:
        return False
    box.clear()
    box.send_keys(code)
    print("===> 已填入回帖验证码: %r" % code)
    return True


# 回执采集：把「本次提交可能写入」的所有位置拼成一段文本。
_REPLY_BLOB_JS = """
            var parts = [];
            var scripts = document.getElementsByTagName('script');
            for (var i = 0; i < scripts.length; i++) parts.push(scripts[i].textContent || '');
            var ret = document.getElementById('fastpostreturn');
            if (ret) {
              var clone = ret.cloneNode(true);
              var wait = clone.querySelector('#fastpostreturn_wait');
              if (wait && wait.parentNode) wait.parentNode.removeChild(wait);
              parts.push(clone.innerHTML || '');
            }
            var mt = document.getElementById('messagetext');
            if (mt) parts.push(mt.textContent || '');
            return parts.join('\\n');
            """


def collect_reply_blob(driver):
    """采集回帖判定用的页面文本快照（为什么扫这些位置见 classify_reply_blob）。"""
    try:
        return driver.execute_script(_REPLY_BLOB_JS) or ""
    except WebDriverException:
        return ""


def _reply_snippet(blob, marker, back=20, width=100):
    """取 marker 所在处的**整句话**。

    只报 marker 本身等于没报：泛短语会把具体原因砍掉（见 classify_reply_blob 第 3 条）。
    """
    index = blob.find(marker)
    if index < 0:
        return marker
    # 向前带一点上下文找句首，再按标签/换行截断 —— Discuz 的提示是纯文本，
    # 后面常跟 `<a>`「如果您的浏览器没有自动跳转，请点击此链接」这类尾巴。
    tail = blob[max(0, index - back) : index + width]
    tail = re.split(r"[<\n\r]", tail)[-1]
    return " ".join(tail.split())[:width] or marker


def classify_reply_blob(blob, baseline=""):
    """纯函数：判定回帖结果 → (归类, 说明)；归类 ∈ success / error / pending / none。

    ⚠️ 三个坑（前两个是 2026-09-27 用 CDP 抓网络日志、第三个是 2026-09-28 在 CI 上踩的）：
      1. Discuz 的响应是**注入到 `<head>` 的一段 `<script>`**，不是写进 `#fastpostreturn`；
      2. `#fastpostreturn` 里有个**隐藏的** `#fastpostreturn_wait`（内容恒为「请稍候...」），
         `textContent` 连隐藏文本一起读 —— 只读它的话**每次都只读到「请稍候...」**，
         结果就是「回复其实成功了，脚本却一直等到超时」；
      3. **命中多个短语时要取最长的那条，并把整句话带出来**，且先与提交前基线做差分。
         否则「抱歉，您两次发表间隔少于 15 秒」会被兜底短语「抱歉，您」吃掉，
         日志里只剩 3 个字，拿着 artifact 也定位不了。
    """

    def fresh(markers):
        """只认「本次提交新引入」的短语 —— 页面固有文本不算数。"""
        return [m for m in markers if blob.count(m) > baseline.count(m)]

    if fresh(REPLY_SUCCESS_MARKERS):

        pid = re.search(r"pid=(\d+)", blob)
        page = re.search(r"page=(\d+)", blob)
        return "success", "pid=%s page=%s" % (
            pid.group(1) if pid else "?",
            page.group(1) if page else "?",
        )

    pending = fresh(REPLY_PENDING_MARKERS)
    if pending:
        return "pending", _reply_snippet(blob, max(pending, key=len))

    hits = fresh(REPLY_ERROR_MARKERS)
    if hits:
        return "error", _reply_snippet(blob, max(hits, key=len))
    return "none", ""


def read_reply_result(driver, baseline=""):
    """读回帖结果 → (归类, 说明)；归类 ∈ success / error / pending / none。

    baseline 传「点击提交前」采集的快照，用于剔除页面固有文本（传空串则不做差分）。
    """
    return classify_reply_blob(collect_reply_blob(driver), baseline)


def read_last_post_text(driver):
    """读帖子列表里最后一层楼（`#postlist` 的最后一个 `div[id^=post_]`）的文字。

    回帖成功后站点会跳到新楼层，末楼就是我们的回复 —— 用它做「确实发出去了」的证据。
    """
    try:
        return " ".join((driver.execute_script("""
                var list = document.getElementById('postlist');
                if (!list) return '';
                var items = list.querySelectorAll("div[id^='post_']");
                if (!items.length) return '';
                return (items[items.length - 1].textContent || '');
                """) or "").split())
    except WebDriverException:
        return ""


def reply_thread(driver, url, text, secrets=()):
    """打开帖子 → 快捷回复框填内容 → 提交 → 按服务端回执确认。

    校验不看界面：Discuz 把回执作为 `<script>` 注入 `<head>`，本主题没定义
    `succeedhandle_fastpost`，所以成功也不会跳转、界面毫无变化（见 read_reply_result）。

    提交前先采一次页面文本基线（`collect_reply_blob`），判定只认**本次新引入**的
    短语，并把服务端原话整句带进日志与异常 —— 见 classify_reply_blob。

    """
    if not pass_waf(driver, url):
        raise RuntimeError("帖子页：WAF 图片验证码未通过（%s）" % url)
    wait_document_ready(driver)
    time.sleep(1.5)

    box, _ = wait_visible(driver, REPLY_BOX_XPATHS, 20, "快捷回复输入框")
    if box is None:
        dump_debug(
            driver,
            "reply_no_box",
            notes=["帖子页没找到快捷回复框（可能权限不足/页面结构变了）"],
            secrets=secrets,
        )
        raise RuntimeError("未找到快捷回复框：%s" % driver.current_url)

    fill_post_captcha(driver)

    box.clear()
    box.send_keys(text)
    print("===> 已在快捷回复框填入: %r" % text)

    submit, _ = wait_visible(driver, REPLY_SUBMIT_XPATHS, 10, "发表回复按钮")
    if submit is None:
        dump_debug(
            driver,
            "reply_no_submit",
            notes=["没找到发表回复按钮"],
            secrets=secrets,
        )
        raise RuntimeError("未找到发表回复按钮：%s" % driver.current_url)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)

    # 提交前的页面文本基线：判定只认「本次新引入」的短语，页面固有文本不算数
    baseline = collect_reply_blob(driver)

    # 记一次文档时间戳：万一站点主题里有 succeedhandle_fastpost（会跳转），靠它兜底
    origin_before = _document_time_origin(driver)
    submit.click()
    print("===> 已点击发表回复")

    deadline = time.time() + 30
    detail = ""
    while time.time() < deadline:
        time.sleep(1)

        kind, detail = read_reply_result(driver, baseline)
        if kind == "success":
            print("===> 回帖成功（服务端回执确认，%s）" % detail)
            return "回帖成功（%s）" % detail
        if kind == "pending":
            # 审核 ≠ 失败：回复已经提交出去了，只是要人工过一遍
            print("===> 回帖已提交，等待审核（%s）" % detail)
            return "已提交待审核（%s）" % detail

        if kind == "error":
            dump_debug(
                driver,
                "reply_rejected",
                notes=["服务端回执: %s" % detail],
                secrets=secrets,
            )
            raise RuntimeError("回帖被拒（%s）" % detail)

        # 部分主题定义了 succeedhandle_fastpost → 会跳到新楼层，用新楼层内容兜底确认
        if _document_time_origin(driver) != origin_before:
            wait_document_ready(driver)
            time.sleep(2)
            last = read_last_post_text(driver)
            if text.strip() and text.strip() in last:
                print("===> 回帖成功（已跳转，新楼层含回复内容）")
                return "回帖成功"
            dump_debug(
                driver,
                "reply_jumped_but_unverified",
                notes=["页面已跳转但没能确认新楼层内容", "末楼文本: %s" % last[:200]],
                secrets=secrets,
            )
            raise RuntimeError("页面已跳转但未确认到回复内容：%s" % driver.current_url)
        if detail:
            print("===> 回帖回执（暂未判定）: %s" % detail[:120])

    # 没判定出来时，把页面文本尾部一并留在现场 —— 否则 artifact 里只有一句「回执片段: (空)」
    tail = " ".join(collect_reply_blob(driver).split())[-300:]
    dump_debug(
        driver,
        "reply_unconfirmed",
        notes=[
            "点击发表回复后 30s 内没拿到明确回执",
            "回执片段: %s" % (detail[:200] or "(空)"),
            "页面文本尾部: %s" % (tail or "(空)"),
        ],
        secrets=secrets,
    )
    raise RuntimeError("点击发表回复后状态未明（%s）" % (detail[:120] or "空"))


def notify(bot_id, status, note="", points="", reply="", credits=""):
    """推一张飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append("**当前积分**: %s" % (points or "未读取到"))
    content.append("**吾爱币**: %s" % ("%s CB" % credits if credits else "未读取到"))
    if reply:
        content.append("**回帖**: %s" % reply)
    if note:
        content.append("**错误信息**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        Feishu_SendCardMsg(bot_id, " 52pojie 签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """解析凭据。**52pojie 只用 Cookie 登录**（2026-09-28 定稿）：

    密码登录这条路已经拆掉 —— 登录页是 Cloudflare Turnstile，而本机网络**根本连不上
    challenges.cloudflare.com**（域名可解析、HTTPS 10s 超时），验证码组件加载不出来；
    CI（美国 IP）那边会话又跟环境相关，时好时坏。所以只保留 Cookie 复用登录态。
    """
    return {
        "cookie": (os.getenv(PJ52_COOKIE_ENV) or "").strip(),
        "bot_id": os.getenv("FEISHU_BOT_ID") or (argv[1] if len(argv) > 1 else ""),
    }


def pojie52(cookie="", bot_id=""):
    def _n(value):
        return len(value or "")

    print("===> 凭据检查: cookie=%d字 / FEISHU_BOT_ID=%d字" % (_n(cookie), _n(bot_id)))
    if not cookie:
        sys.exit(
            "[X] 没有 Cookie。52pojie 只用 Cookie 登录（密码登录走不通：登录页是"
            " Cloudflare Turnstile，本机网络连不上 challenges.cloudflare.com）。\n"
            "    请设置 %s —— 取法见 LOCAL_RUN.md：浏览器登录后 F12 → Network → 刷新 →\n"
            "    点 Document 请求 → Request Headers 里的 cookie 整行（或右键 Copy as cURL）。"
            % PJ52_COOKIE_ENV
        )

    status = "签到失败"
    note = ""
    points = ""
    credits = ""
    reply_status = ""
    driver = get_web_driver()
    try:
        print("===> 使用 Cookie 登录态，跳过登录页")
        pairs = parse_cookie_header(cookie)
        # 名字不是机密（Discuz 的 cookie 名固定），值绝不打印 —— 出问题时靠这份清单定位
        print(
            "===> Cookie 项(%d): %s"
            % (len(pairs), ", ".join(name for name, _ in pairs))
        )
        missing = check_cookie_completeness(pairs)
        # 仓库公开、artifact 谁都能下：把 cookie 的值也当机密抹掉。
        # 只抹长度 >=6 的 —— 短值（sid=0、atarget=1）会把名字清单里的
        # 每一位数字都替换成 ***，把诊断信息本身毁掉。
        secrets = tuple(value for _, value in pairs if len(value) >= 6)

        inject_cookies(driver, cookie, COOKIE_DOMAIN)
        pass_waf(driver, HOME_URL)
        if not is_logged_in(driver):
            # 最常见的两种原因分开说：抄漏了 auth/saltkey，或者会话真过期了
            hint = (
                "；**缺 %s**，说明这份 Cookie 不是从请求头里取的（document.cookie 看不到 HttpOnly 项）"
                % " / ".join("*" + name for name in missing)
                if missing
                else "（auth/saltkey 都在，应是会话已过期/环境对不上）"
            )
            dump_debug(
                driver,
                "cookie_invalid",
                notes=[
                    "注入 Cookie 后首页仍非登录态" + hint,
                    "cookie 项: %s" % ", ".join(name for name, _ in pairs),
                ],
                secrets=secrets,
            )
            raise RuntimeError(
                "注入的 Cookie 无效或已过期%s\n"
                "    重新取一份（浏览器登录 52pojie → Network → Copy as cURL）更新 %s 即可。"
                % (hint, PJ52_COOKIE_ENV)
            )
        print("===> Cookie 登录态有效")

        status = sign_in(driver, secrets)
        print("===> 签到结果: %s" % status)

        if REPLY_ENABLE:
            title, href = pick_thread(driver, FORUM_URL, secrets)
            try:
                reply_status = "%s（%s）" % (
                    reply_thread(driver, href, REPLY_TEXT, secrets),
                    title[:24],
                )
            except Exception as err:
                reply_status = "失败：%s" % str(err)[:120]
                print("===> 回帖失败: %s" % err)
                if REPLY_STRICT:
                    raise
            print("===> 回帖结果: %s" % reply_status)
        else:
            print("===> PJ52_REPLY=0，跳过回帖")

        # 积分/吾爱币放在**回帖之后**读：回帖本身 +1 吾爱币，
        # 先读的话卡片上就是回帖前的旧值（lodge 2026-09-29 要求读的是回帖后的数）。
        driver.get(HOME_URL)
        pass_waf(driver, HOME_URL)
        time.sleep(1)
        points = read_points(driver)
        print("===> 当前积分: %s" % (points or "未读取到"))

        credits = read_credits(driver)
        print("===> 当前吾爱币: %s" % ("%s CB" % credits if credits else "未读取到"))
    except Exception as err:
        status = "签到失败"
        note = str(err)[:200]
        raise
    finally:
        try:
            driver.quit()
        except Exception as err:
            print("[WARN] 关闭浏览器失败: %s" % err)
        if bot_id:
            notify(bot_id, status, note, points, reply_status, credits)


if __name__ == "__main__":
    if len(sys.argv) == 1 and not os.getenv("PJ52_COOKIE"):
        sys.exit(
            "用法: python -m Selenium.CheckIN.52pojie\n"
            "  凭据只走环境变量 PJ52_COOKIE（取法见 LOCAL_RUN.md）\n"
            "  可选: python -m ... <飞书机器人 webhook>"
        )
    pojie52(**resolve_credentials(sys.argv))
