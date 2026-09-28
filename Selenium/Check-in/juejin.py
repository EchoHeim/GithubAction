# -*- coding: UTF-8 -*-
"""掘金（juejin.cn）签到：密码登录（自动过滑块验证码）→ 每日签到页点「立即签到」→ 读矿石数。

━━━ 登录：密码 + 滑块验证码（已实现，但服务端行为风控可能仍拦）━━━
2026-09-27 实测：点「登录」后站点会弹**字节验证中心的滑块验证码**，它在 iframe 里：
```
iframe : https://rmc.bytedance.com/verifycenter/captcha/v2?from=iframe&fp=verify_xxx
  背景图 <img id="captcha_verify_image">        渲染 340x212 / 原始 552x344
  拼图块 <img id="captcha-verify_img_slide">     渲染 68x68  / 原始 110x110
  拖动钮 <div class="captcha-slider-btn">
验证接口 POST //verify.zijieapi.com/captcha/verify?aid=2608&...&subtype=slide
```
**位置识别+拖动这条路已经打通**（实测数据见 LOCAL_RUN.md）：缺口命中置信度 0.95~0.99、拼图块位移
与计算距离**逐像素吻合**、CDP 派发的轨迹点间隔 16~50ms/总时长 1.2~1.5s。
但服务端仍不给通过态：轨迹**过快/成对 0ms** 时会回
`{"code":502,"message":"操作过快，请慢一点[5014]"}`，平滑拟人轨迹则被**静默评分拒绝** ——
字节那套是 ML 行为风控，合成事件很难稳定过。所以：
  * 密码登录照跑（`JUEJIN_MAX_ATTEMPTS` 轮，每轮换一张图重试）；
  * 失败且配了 `JUEJIN_COOKIE` 时**自动降级**用 Cookie，保证签到本身能完成。

━━━ 签到流程 ━━━
`/user/center/signin` 是「每日签到」页：左侧日历 + 右侧大按钮「立即签到」，
页面上还有「连续签到天数 / 累计签到天数 / 当前矿石数」。脚本：
  1. 登录（或复用 Cookie 登录态）→ 打开签到页；
  2. 读签到前状态：矿石数、连续/累计天数、按钮文案；
  3. 按钮已是「已签到」类文案 → 判「今日已签到」，直接结束；
  4. 否则点「立即签到」，按**多重判据**确认成功（按钮文案变化 / 矿石数变化 /
     连续天数 +1 / 出现「签到成功」提示），拿不到就 dump 现场后抛错。

用法（凭据走环境变量）：
    JUEJIN_USERNAME=手机号 JUEJIN_PASSWORD=密码 python -m Selenium.Check-in.juejin
    # 兼容老写法：python -m ... <手机号/邮箱> <密码> [飞书机器人 webhook]

可选环境变量：
    JUEJIN_USERNAME      账号（手机号/邮箱）
    JUEJIN_PASSWORD      密码
    JUEJIN_COOKIE        登录态 Cookie（可选兜底：走 Cookie 时跳过登录页与滑块）
    FEISHU_BOT_ID        飞书机器人 webhook，给了才推卡片（含签到状态 + 矿石数）
    JUEJIN_SIGNIN_URL    签到页，默认 https://juejin.cn/user/center/signin
    JUEJIN_MAX_ATTEMPTS  整轮重来的次数，默认 3
    JUEJIN_HOME_URL      首页，默认 https://juejin.cn/

失败现场写进 juejin-debug/，CI 里由 workflow 收集成 artifact。
"""

import base64
import math
import os
import random
import re
import sys
import time

import cv2
import numpy as np

from Selenium.base import *
from Messaging.Feishu import Feishu_SendCardMsg

HOME_URL = os.getenv("JUEJIN_HOME_URL", "https://juejin.cn/")
SIGNIN_URL = os.getenv("JUEJIN_SIGNIN_URL", "https://juejin.cn/user/center/signin")
MAX_ATTEMPTS = int(os.getenv("JUEJIN_MAX_ATTEMPTS", "3"))

JUEJIN_COOKIE_ENV = "JUEJIN_COOKIE"
COOKIE_DOMAIN = ".juejin.cn"

DEBUG_DIR = os.path.join(os.getcwd(), "juejin-debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# 首页「登录」按钮：它不存在 = 已登录
LOGIN_BUTTON_XPATHS = (
    "//button[@class='login-button']",
    "//button[contains(@class,'login-button')]",
    "//button[normalize-space(text())='登录']",
)
# 弹层里切到密码登录
PASSWORD_TAB_XPATHS = (
    "//span[contains(@class,'clickable') and contains(text(),'密码登录')]",
    "//*[contains(@class,'clickable') and normalize-space(text())='密码登录']",
)
USERNAME_XPATHS = (
    "//input[@name='loginPhoneOrEmail']",
    "//input[contains(@placeholder,'邮箱') or contains(@placeholder,'手机号')]",
)
PASSWORD_XPATHS = (
    "//input[@name='loginPassword']",
    "//input[@type='password' and contains(@class,'login-password')]",
)
SUBMIT_XPATHS = (
    "//button[contains(@class,'btn-login')]",
    "//button[normalize-space(text())='登录' and not(contains(@class,'register'))]",
)
# 风控指纹：出现这些就是「要你扫码验身」，别再试密码了
RISK_MARKERS = ("扫码验证", "抖音 APP", "使用已登录账号的设备扫码")

# ── 滑块验证码（字节验证中心，跑在 iframe 里）──
# 实测（2026-09-27）：点登录后弹出
#   iframe: https://rmc.bytedance.com/verifycenter/captcha/v2?from=iframe&fp=verify_xxx
# 内部元素（在 iframe 内定位，必须先 switch_to.frame）：
#   背景图  <img id="captcha_verify_image" class="captcha-verify-image">   渲染 340x212 / 原始 552x344
#   拼图块  <img id="captcha-verify_img_slide" ...>                        渲染 68x68 / 原始 110x110
#   拖动钮  <div class="captcha-slider-btn">
#   刷新    <div class="vc-captcha-refresh">
CAPTCHA_FRAME_XPATHS = (
    "//iframe[contains(@src,'verifycenter/captcha')]",
    "//iframe[contains(@src,'rmc.bytedance.com')]",
)
CAPTCHA_BG_XPATHS = ("//*[@id='captcha_verify_image']", "//*[contains(@class,'captcha-verify-image')]")
CAPTCHA_PIECE_XPATHS = ("//*[@id='captcha-verify_img_slide']",)
CAPTCHA_HANDLE_XPATHS = (
    "//*[contains(@class,'captcha-slider-btn')]",
    "//*[contains(@class,'dragger-item')]",
)
CAPTCHA_REFRESH_XPATHS = ("//*[contains(@class,'vc-captcha-refresh')]",)
CAPTCHA_FAIL_MARKERS = ("验证失败", "请重试", "再试一次", "拖动滑块")

FETCH_AS_DATA_URL_JS = """
var cb = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: 'omit'}).then(function(r){ return r.blob(); }).then(function(b){
  var fr = new FileReader();
  fr.onload = function(){ cb(fr.result); };
  fr.readAsDataURL(b);
}).catch(function(e){ cb('ERR:' + e); });
"""

# 签到按钮：按**文案**找，别认哈希类名（掘金的 class 随构建变）
SIGNIN_BUTTON_XPATHS = (
    "//button[normalize-space(text())='立即签到']",
    "//button[contains(text(),'立即签到')]",
    "//*[contains(@class,'signin') and contains(text(),'立即签到')]",
    "//*[normalize-space(text())='立即签到']",
)
SIGNIN_DONE_MARKERS = ("已签到", "今日已签到", "明天再来", "已领取")
SIGNIN_SUCCESS_MARKERS = ("签到成功", "领取成功", "获得", "恭喜")
# 页面上「当前矿石数 / 连续签到天数 / 累计签到天数」的取值
ORES_PATTERN = r"当前矿石数\D{0,20}?(\d[\d,]*)"
STREAK_PATTERN = r"连续签到天数\D{0,20}?(\d+)"
TOTAL_PATTERN = r"累计签到天数\D{0,20}?(\d+)"


def _safe_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)
    except OSError as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (path, err))


def page_text(driver):
    """整页可见文本（压缩空白）——掘金是 SPA，取 body.innerText 最省事。"""
    try:
        return " ".join(
            (driver.execute_script("return document.body.innerText || '';") or "").split()
        )
    except WebDriverException:
        return ""


def dump_debug(driver, tag, notes=(), secrets=()):
    """留存失败现场：URL、页面文案、DOM、截图（入库前抹掉凭据）。"""
    prefix = os.path.join(DEBUG_DIR, "%s_%s" % (tag, time.strftime("%H%M%S")))

    info = []
    try:
        info.append("url: %s" % driver.current_url)
        info.append("title: %s" % driver.title)
    except WebDriverException as err:
        info.append("url/title 读取失败: %s" % err)
    info.append("页面文本: %s" % page_text(driver)[:300])
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
        # 只抹够长的值：短值（如 1、0）会把诊断文本里的数字全打成 ***
        if secret and len(secret) >= 6:
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


def is_logged_in(driver):
    """登录态判据：`sessionid` cookie 存在，或页面上找不到登录按钮。"""
    try:
        if driver.get_cookie("sessionid"):
            return True
    except WebDriverException:
        pass
    try:
        if "juejin.cn" in (driver.current_url or ""):
            return find_visible(driver, LOGIN_BUTTON_XPATHS)[0] is None
    except WebDriverException:
        pass
    return False


def risk_control_hit(driver):
    """是否命中「请用抖音 APP 扫码验证」的风控文案。"""
    text = page_text(driver)
    return any(marker in text for marker in RISK_MARKERS)


def fetch_bytes(driver, url):
    """在当前页面上下文里把图片抓成 bytes（走浏览器，带 referer，避免 CDN 直接请求被拒）。"""
    data_url = driver.execute_async_script(FETCH_AS_DATA_URL_JS, url)
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        raise RuntimeError("取图失败: %s" % str(data_url)[:80])
    return base64.b64decode(data_url.split(",", 1)[1])


def slider_offset(bg_bytes, piece_bytes):
    """算缺口左边缘到背景左边缘的距离（**原始图片像素**），返回 (loc, 置信度)。

    关键：拼图块是「亮版」内容，背景上的缺口是**压暗**过的，直接按像素匹配会匹配到
    云/岩石上（实测置信度 0.80 落在云里）。改用带 alpha 掩码的 `TM_CCOEFF_NORMED` ——
    它对线性明暗变化不敏感，实测 0.93 且二维落点正落在缺口上。
    掩码先腐蚀一圈，把拼图块自带的白色描边剔掉，否则会拉低相关。
    """
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    piece = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if bg is None or piece is None:
        raise RuntimeError("图片解码失败")
    if piece.shape[2] == 4:
        alpha = piece[:, :, 3]
    else:
        alpha = np.full(piece.shape[:2], 255, np.uint8)
    gray = cv2.cvtColor(piece[:, :, :3], cv2.COLOR_BGR2GRAY)
    mask = cv2.erode((alpha > 128).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    res = cv2.matchTemplate(bg, gray, cv2.TM_CCOEFF_NORMED, mask=mask)
    _, score, _, loc = cv2.minMaxLoc(res)
    return loc, float(score)


def human_track(distance):
    """生成拖动轨迹（ActionChains 回退路径用）：easeInOut 曲线 + 抖动。"""
    if distance <= 0:
        return []
    steps = max(10, min(28, distance // 8 or 10))
    track = []
    prev = 0.0
    for i in range(1, steps + 1):
        eased = 0.5 - 0.5 * math.cos(math.pi * i / steps)   # easeInOutSine
        pos = distance * eased
        track.append(pos - prev + random.uniform(-0.8, 0.8))  # 加抖动
        prev = pos
    track[-1] += distance - sum(track)                        # 补齐到精确距离
    return [max(1, int(round(abs(s)))) for s in track]


def human_points(distance, duration):
    """返回 [(x, t)]：先加速后减速 + 抖动 + 末尾小幅过冲再回拉（更像人手的收尾）。"""
    steps = max(18, min(60, int(distance / 2.5) or 20))
    points = []
    for i in range(1, steps + 1):
        frac = i / steps
        eased = 0.5 - 0.5 * math.cos(math.pi * frac)
        points.append([
            distance * eased + random.uniform(-0.7, 0.7),
            duration * frac + random.uniform(-duration * 0.02, duration * 0.02),
        ])
    overshoot = random.uniform(1.0, 3.0)
    points.append([distance + overshoot, duration + random.uniform(0.05, 0.12)])
    points.append([distance, duration + random.uniform(0.15, 0.30)])
    points.sort(key=lambda p: p[1])
    return points


def drag_by_cdp(driver, handle_x, handle_y, distance, duration):
    """用 CDP `Input.dispatchMouseEvent` 派发拖动，并**显式指定时间戳**。

    为什么不用 ActionChains：每个 `perform()` 都是一次 WebDriver 往返，实测每步约 0.3s
    （70 步要 21 秒），时间完全不可控；而且同一帧会产生成对的 pointer/mouse 事件，
    服务端看到 0ms 间隔会判「操作过快」。CDP 这条路能精确控速（实测点间隔 16~50ms）。

    坐标要点：**CDP 用顶层视口坐标**，而 Selenium 在 iframe 内给的是 iframe 局部坐标，
    所以调用方必须先把 iframe 的 rect 偏移加进来（否则按下点打空、滑块纹丝不动）。
    """
    base = time.time()
    # 先移到手柄上「停一下」，再按下 —— 直接瞬移+按下更像脚本
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": handle_x, "y": handle_y, "button": "none"})
    time.sleep(random.uniform(0.2, 0.5))
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": handle_x, "y": handle_y, "button": "left",
        "buttons": 1, "clickCount": 1, "timestamp": base})
    time.sleep(random.uniform(0.15, 0.35))

    for x, t in human_points(distance, duration):
        timestamp = base + t
        wait = timestamp - time.time()
        if wait > 0:
            time.sleep(wait)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": handle_x + x,
            "y": handle_y + random.choice([0, 0, 0, 0, 1, -1]),
            "button": "left", "buttons": 1, "timestamp": timestamp})

    time.sleep(random.uniform(0.1, 0.25))
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": handle_x + distance, "y": handle_y,
        "button": "left", "buttons": 0, "clickCount": 1, "timestamp": time.time()})
    return time.time() - base


def drag_by_actions(driver, handle, distance):
    """回退方案：ActionChains（CDP 不可用时）。"""
    ActionChains(driver).move_to_element(handle).click_and_hold().perform()
    time.sleep(random.uniform(0.15, 0.35))
    for step in human_track(distance):
        ActionChains(driver).move_by_offset(step, 0).perform()
        time.sleep(random.uniform(0.008, 0.022))
    time.sleep(random.uniform(0.2, 0.5))
    ActionChains(driver).release().perform()


def captcha_present(driver):
    """父页面里是否还挂着验证 iframe。"""
    try:
        driver.switch_to.default_content()
    except WebDriverException:
        pass
    try:
        return len(driver.find_elements(By.XPATH, CAPTCHA_FRAME_XPATHS[0])) > 0
    except WebDriverException:
        return False


def click_captcha_refresh(driver):
    element, _ = find_visible(driver, CAPTCHA_REFRESH_XPATHS)
    if element is None:
        print("[WARN] 找不到验证码刷新按钮")
        return
    try:
        element.click()
        time.sleep(1.5)
    except WebDriverException as err:
        print("[WARN] 刷新验证码失败: %s" % err)


def solve_slider(driver, max_rounds=4):
    """过字节滑块验证码；返回是否通过（判据：父页面里的验证 iframe 消失）。"""
    frame, _ = wait_visible(driver, CAPTCHA_FRAME_XPATHS, 25, "验证 iframe")
    if frame is None:
        return False
    # iframe 在**顶层页面**里的偏移：CDP 派发鼠标事件用的是顶层视口坐标，
    # 而 Selenium 在 iframe 内取到的是 iframe 局部坐标 —— 必须把这段偏移补上。
    try:
        frame_rect = frame.rect
        frame_x, frame_y = frame_rect["x"], frame_rect["y"]
    except WebDriverException:
        frame_x, frame_y = 0, 0
    print("===> 验证 iframe 顶层偏移: (%d, %d)" % (frame_x, frame_y))

    for round_no in range(1, max_rounds + 1):
        driver.switch_to.frame(frame)
        try:
            bg, _ = wait_visible(driver, CAPTCHA_BG_XPATHS, 15, "拼图背景图")
            piece, _ = wait_visible(driver, CAPTCHA_PIECE_XPATHS, 15, "拼图小块")
            handle, _ = wait_visible(driver, CAPTCHA_HANDLE_XPATHS, 15, "拖动按钮")
            if bg is None or piece is None or handle is None:
                print("[WARN] 验证码元素没找全（背景/小块/拖动钮）")
                return False

            # 等图片真的加载完再取尺寸：没加载完时 naturalWidth=0，比例会算错
            load_deadline = time.time() + 15
            while time.time() < load_deadline:
                if int(bg.get_attribute("naturalWidth") or 0) > 0:
                    break
                time.sleep(0.3)

            rendered_w = bg.size["width"]
            natural_w = int(bg.get_attribute("naturalWidth") or 0)
            bg_bytes = fetch_bytes(driver, bg.get_attribute("src"))
            piece_bytes = fetch_bytes(driver, piece.get_attribute("src"))
            (natural_x, natural_y), score = slider_offset(bg_bytes, piece_bytes)
            scale = (rendered_w / float(natural_w)) if natural_w else 0
            if not natural_w:
                # 图片没加载完时 naturalWidth=0，比例会退化成 1.0，拖动距离直接算错
                # （2026-09-27 CI 第 1 轮就是这么废掉的：比例 1.0000、拖了 295px）
                print("[WARN] 背景图还没加载完（naturalWidth=0），换一张重来")
                click_captcha_refresh(driver)
                continue
            distance = int(round(natural_x * scale))
            print(
                "===> 第 %d/%d 轮: 缺口命中 %s(原始像素) 置信度 %.3f → 拖动 %d px（比例 %.4f）"
                % (round_no, max_rounds, (natural_x, natural_y), score, distance, scale)
            )
            if distance <= 0:
                print("[WARN] 算出的拖动距离非正，刷新重来")
                click_captcha_refresh(driver)
                continue

            # 拖动：优先 CDP（时长精确可控），失败再回退 ActionChains
            duration = random.uniform(0.9, 1.5)
            handle_rect = handle.rect
            handle_x = frame_x + handle_rect["x"] + handle_rect["width"] / 2.0
            handle_y = frame_y + handle_rect["y"] + handle_rect["height"] / 2.0
            try:
                real = drag_by_cdp(driver, handle_x, handle_y, distance, duration)
                print("===> 已释放滑块（CDP 拖动，计划 %.2fs / 实际 %.2fs）" % (duration, real))
            except WebDriverException as err:
                print("[WARN] CDP 拖动不可用(%s)，回退 ActionChains" % str(err)[:60])
                drag_by_actions(driver, handle, distance)
                print("===> 已释放滑块（ActionChains 回退）")
        finally:
            try:
                driver.switch_to.default_content()
            except WebDriverException:
                pass

        deadline = time.time() + 8
        while time.time() < deadline:
            if not captcha_present(driver):
                print("===> 滑块验证通过（验证 iframe 已消失）")
                return True
            time.sleep(0.5)

        print("===> 滑块未通过，换一张重试")
        frame, _ = find_visible(driver, CAPTCHA_FRAME_XPATHS)
        if frame is None:
            return True
        driver.switch_to.frame(frame)
        try:
            click_captcha_refresh(driver)
        finally:
            try:
                driver.switch_to.default_content()
            except WebDriverException:
                pass
        time.sleep(2)

    return not captcha_present(driver)


def login_once(driver, username, password, attempt=1):
    """密码登录：提交后若弹出滑块验证码就自动拖过去。"""
    driver.get(HOME_URL)
    time.sleep(3)
    if is_logged_in(driver):
        print("===> 已是登录态（cookie 复用），跳过登录")
        return True

    button, _ = wait_visible(driver, LOGIN_BUTTON_XPATHS, 20, "首页登录按钮")
    if button is None:
        raise NoSuchElementException("首页未找到登录按钮")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    button.click()
    time.sleep(2)

    tab, _ = wait_visible(driver, PASSWORD_TAB_XPATHS, 15, "密码登录入口")
    if tab is None:
        raise NoSuchElementException("登录弹层未找到「密码登录」入口")
    tab.click()
    time.sleep(1.5)

    user, _ = wait_visible(driver, USERNAME_XPATHS, 15, "账号输入框")
    pwd, _ = wait_visible(driver, PASSWORD_XPATHS, 15, "密码输入框")
    if user is None or pwd is None:
        raise NoSuchElementException("密码登录面板未找到账号/密码输入框")
    user.clear()
    user.send_keys(username)
    pwd.clear()
    pwd.send_keys(password)

    submit, _ = wait_visible(driver, SUBMIT_XPATHS, 10, "登录提交按钮")
    if submit is None:
        raise NoSuchElementException("登录弹层未找到提交按钮")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
    submit.click()
    time.sleep(4)

    # 提交后站点多半弹滑块验证码（字节验证中心 iframe），过掉它才继续登录
    if captcha_present(driver):
        print("===> 命中滑块验证码，开始自动拖动")
        if not solve_slider(driver):
            dump_debug(driver, "a%d_slider_failed" % attempt, secrets=(username, password))
            raise RuntimeError("滑块验证码未通过（已重试多轮）")
        time.sleep(3)

    for _ in range(6):
        if is_logged_in(driver):
            print("===> 登录成功")
            return True
        if risk_control_hit(driver):
            dump_debug(driver, "a%d_risk_control" % attempt, secrets=(username, password))
            raise RuntimeError(
                "掘金要求用「抖音 APP」扫码验证（账号风控），这条流程自动化走不通"
            )
        time.sleep(2)

    dump_debug(driver, "a%d_login_timeout" % attempt, secrets=(username, password))
    return False


def read_numbers(driver):
    """读签到页上的矿石数 / 连续天数 / 累计天数；读不到为 None。"""
    text = page_text(driver)

    def pick(pattern):
        match = re.search(pattern, text)
        return match.group(1).replace(",", "") if match else None

    return {
        "ores": pick(ORES_PATTERN),
        "streak": pick(STREAK_PATTERN),
        "total": pick(TOTAL_PATTERN),
    }


def sign_in(driver, username="", password=""):
    """签到：打开每日签到页 → 点「立即签到」→ 多重判据确认结果。"""
    driver.get(SIGNIN_URL)
    time.sleep(5)

    if not is_logged_in(driver):
        dump_debug(
            driver,
            "signin_not_logged_in",
            notes=["签到页不是登录态：url=%s" % driver.current_url],
            secrets=(username, password),
        )
        raise RuntimeError("签到页不是登录态：url=%s" % driver.current_url)

    before = read_numbers(driver)
    print(
        "===> 签到前: 矿石数=%s 连续=%s 累计=%s"
        % (before["ores"] or "?", before["streak"] or "?", before["total"] or "?")
    )

    text = page_text(driver)
    button, hit = find_visible(driver, SIGNIN_BUTTON_XPATHS)
    if button is None:
        if any(marker in text for marker in SIGNIN_DONE_MARKERS):
            print("===> 没有「立即签到」按钮，但页面出现已签到文案")
            return "今日已签到（跳过）", before
        dump_debug(
            driver,
            "signin_no_button",
            notes=["签到页既没有「立即签到」按钮，也没有已签到文案（页面结构可能变了）"],
            secrets=(username, password),
        )
        raise RuntimeError("签到页未找到签到按钮：url=%s" % driver.current_url)

    button_text = (button.text or "").strip()
    print("===> 找到签到按钮: %r（选择器 %s）" % (button_text, hit))
    if any(marker in button_text for marker in SIGNIN_DONE_MARKERS):
        return "今日已签到（跳过）", before

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    button.click()
    print("===> 已点击「立即签到」")

    deadline = time.time() + 20
    after = before
    while time.time() < deadline:
        time.sleep(1)
        after = read_numbers(driver)
        now_text = page_text(driver)

        # 判据一：数字变了（矿石 +X / 连续天数 +1）
        if after["ores"] != before["ores"] or after["streak"] != before["streak"]:
            print("===> 签到成功（数字变化: 矿石 %s -> %s）" % (before["ores"], after["ores"]))
            return "签到成功", after
        # 判据二：按钮不再是「立即签到」，且页面出现已签到文案
        left, _ = find_visible(driver, SIGNIN_BUTTON_XPATHS)
        if left is None and any(marker in now_text for marker in SIGNIN_DONE_MARKERS):
            print("===> 签到成功（按钮已转为已签到态）")
            return "签到成功", after
        # 判据三：明确的成功提示
        if any(marker in now_text for marker in SIGNIN_SUCCESS_MARKERS):
            print("===> 签到成功（页面出现成功提示）")
            return "签到成功", after

    dump_debug(
        driver,
        "signin_not_confirmed",
        notes=[
            "点击「立即签到」后 20s 内状态未变化",
            "点击前: 矿石=%s 连续=%s" % (before["ores"], before["streak"]),
            "点击后: 矿石=%s 连续=%s" % (after["ores"], after["streak"]),
        ],
        secrets=(username, password),
    )
    raise RuntimeError("点击「立即签到」后状态未变化，可能未生效")


def notify(bot_id, status, ores="", note=""):
    """推一张飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append("**当前矿石数**: %s" % (ores or "未读取到"))
    if note:
        content.append("**错误信息**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        Feishu_SendCardMsg(bot_id, " 掘金 签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """凭据：环境变量优先，命令行参数兼容。返回 dict，避免位置参数错位。"""
    return {
        "username": os.getenv("JUEJIN_USERNAME") or (argv[1] if len(argv) > 1 else ""),
        # 两种拼写都认：这个仓库的 secret 惯用 *_PASSWD（旧 secret 里 PASSWORD/PASSWD 混着来）
        "password": (os.getenv("JUEJIN_PASSWORD") or os.getenv("JUEJIN_PASSWD")
                     or (argv[2] if len(argv) > 2 else "")),
        "cookie": (os.getenv(JUEJIN_COOKIE_ENV) or "").strip(),
        "bot_id": os.getenv("FEISHU_BOT_ID") or (argv[3] if len(argv) > 3 else ""),
    }


def juejin(username="", password="", cookie="", bot_id=""):
    # 只打**长度**不打内容：数字不会被 GitHub 的 secret 遮蔽机制吃掉，
    # 这样「密码到底有没有传进来」一眼可判（2026-09-27 曾被 *** 遮得看不出）。
    def _n(value):
        return len(value or "")

    print(
        "===> 凭据检查: cookie=%d字 / JUEJIN_USERNAME=%d字 / JUEJIN_PASSWORD=%d字"
        % (_n(cookie), _n(username), _n(password))
    )
    # 变量**名**不是机密，值才是 —— 打出来便于一眼看出「名字对不上/漏传」。
    # 2026-09-27 踩过：账号传进来了、密码却是 0 字，只靠长度看不出是名字拼错还是值空。
    related = sorted(k for k in os.environ if k.upper().startswith(("JUEJIN", "PJ52")))
    print("===> 环境里凭据相关变量名: %s" % (", ".join(related) or "(一个都没有)"))

    if not (username and password) and not cookie:
        sys.exit(
            "[X] 没有可用凭据 | cookie=%d字 username=%d字 password=%d字\n"
            "    请到 仓库 → Settings → Secrets and variables → Actions 逐字符核对：\n"
            "      · 在 **Secrets** 标签页（不是 Variables、不是 Environment secrets）里\n"
            "        有 JUEJIN_USERNAME / JUEJIN_PASSWORD，名字大小写与拼写完全一致；\n"
            "      · 两个 secret 都要有值（重新 Update 时别带首尾空格/换行）；\n"
            "      · 改过 secret 后要重新触发一次 workflow 才生效。"
            % (_n(cookie), _n(username), _n(password))
        )

    status = "签到失败"
    note = ""
    ores = ""
    driver = get_web_driver()
    try:
        # 优先账号密码（会自动过滑块验证码）；滑块被行为风控拦下时，若配了 Cookie 就降级用它
        logged = False
        if username and password:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    if login_once(driver, username, password, attempt):
                        logged = True
                        break
                    print("===> 第 %d 次登录未通过，重试" % attempt)
                except (TimeoutException, NoSuchElementException, ValueError, RuntimeError) as err:
                    # RuntimeError 也要接住：滑块没过时会抛它，不能让整个流程终止 ——
                    # 否则就跳不到下面的 Cookie 兜底了。
                    print("===> 第 %d 次登录异常: %s" % (attempt, err))
                    dump_debug(driver, "a%d_error" % attempt, notes=[repr(err)])
                time.sleep(2)
            if not logged and cookie:
                print("===> 密码登录（含滑块）未通过，降级用 Cookie 登录态")

        if not logged and cookie:
            print("===> 使用 Cookie 登录态，跳过登录页与滑块")
            pairs = parse_cookie_header(cookie)
            print("===> Cookie 项(%d): %s" % (len(pairs), ", ".join(name for name, _ in pairs)))
            inject_cookies(driver, cookie, COOKIE_DOMAIN)
            driver.get(HOME_URL)
            time.sleep(4)
            if not is_logged_in(driver):
                dump_debug(
                    driver,
                    "cookie_invalid",
                    notes=["注入 Cookie 后首页仍非登录态（可能是 sessionid 过期）"],
                    secrets=tuple(value for _, value in pairs if len(value) >= 6),
                )
                raise RuntimeError("注入的 Cookie 无效或已过期，请在浏览器里重新登录后再抄一次")
            print("===> Cookie 登录态有效")
            logged = True

        if not logged:
            dump_debug(driver, "final_failure", notes=["密码登录已尝试 %d 次" % MAX_ATTEMPTS])
            raise RuntimeError("登录失败：已尝试 %d 次（滑块被字节行为风控拦下时请改用 Cookie）" % MAX_ATTEMPTS)

        status, numbers = sign_in(driver, username, password)
        ores = numbers.get("ores") or ""
        print("===> 签到结果: %s（矿石数 %s）" % (status, ores or "未读取到"))
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
            notify(bot_id, status, ores, note)


if __name__ == "__main__":
    if len(sys.argv) == 1 and not any(
        os.getenv(k) for k in ("JUEJIN_COOKIE", "JUEJIN_USERNAME", "JUEJIN_PASSWORD")
    ):
        sys.exit(
            "用法: python -m Selenium.Check-in.juejin\n"
            "  凭据走环境变量: JUEJIN_COOKIE（推荐）/ JUEJIN_USERNAME + JUEJIN_PASSWORD\n"
            "  也兼容老写法: python -m ... <手机号/邮箱> <密码> [飞书机器人 webhook]"
        )
    juejin(**resolve_credentials(sys.argv))
