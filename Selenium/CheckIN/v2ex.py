# -*- coding: UTF-8 -*-
"""V2EX 自动登录 + 每日签到。

验证码识别走本地离线 OCR（ddddocr），不依赖任何打码平台。

⚠️ 登录与领奖**必须在同一个域**：V2EX 的 session cookie（PB3_SESSION）是 host-only，
`v2ex.com` 和 `edge.v2ex.com` 各签各的，互不通用。在 edge.v2ex.com 登录后再去
v2ex.com/mission/daily 会被踢回登录页 —— 所以 SIGNIN_URL 默认指向老站 v2ex.com。
（两站的登录页结构一致：搜索框 → 用户名 → 密码 → 验证码 → 提交，选择器通用。）

靠三层机制保成功率：
  1. 语言无关的定位 —— V2EX 按 Accept-Language 切界面文案，CI 是海外 IP 拿到英文界面，
     所以选择器一律以「密码框」为锚点做结构化定位，再拿中英文 placeholder 做优先匹配。
  2. Ocr_Captcha_Vote —— 换图直到默认模型与 beta 模型结果一致才采信（实测一致即全对），
     换图不计入登录失败次数；拿不到一致结果就整页重来，绝不提交存疑验证码。
  3. 登录重试 —— 仍失败则整页重来，会拿到一张全新的验证码图。

领奖按站点真实路径走（`claim_daily`）：
  回首页确认登录态 → 点侧栏「领取今日的登录奖励」入口 → 任务页点「领取 X 铜币」→ 校验领取结果。
  ⚠️ 领取成功后按钮**不会消失**：V2EX 把它从「领取 X 铜币」改成「查看我的账户余额」。
  所以「按钮消失」「文案不再表达可领取」「页面出现成功提示」三者任一成立即判成功。
  首页入口只在「今天还没领」时存在，所以**没有入口就直接判定「今日已领取」并正常结束**——
  同一天重复跑不会误报失败。每一步都先等 URL 落地再查元素，任何异常都 dump 现场后抛错，
  绝不再出现「打了日志就算成功」。

用法：
    python v2ex.py <用户名> <密码> [飞书机器人 webhook]

签到结束后会往飞书推一张卡片（状态 + 账户余额）。不给第三个参数就不推。

可选环境变量：
    V2EX_SIGNIN_URL     登录页，默认 https://v2ex.com/signin（必须与签到页同域）
    V2EX_HOME_URL       首页，默认 https://v2ex.com/
    V2EX_MISSION_URL    签到页，默认 https://v2ex.com/mission/daily
    V2EX_MAX_ATTEMPTS   整页重来的次数，默认 5
    V2EX_VOTE_ROUNDS    单次登录内换图找一致结果的上限，默认 12

失败现场都会写进 v2ex-debug/，CI 里由 workflow 收集成 artifact——出问题不用再靠猜。
"""

import os
import re
import sys
import time

from Selenium.base import *
from Messaging.Feishu import Feishu_SendCardMsg

SIGNIN_URL = os.getenv("V2EX_SIGNIN_URL", "https://v2ex.com/signin")
HOME_URL = os.getenv("V2EX_HOME_URL", "https://v2ex.com/")
MISSION_URL = os.getenv("V2EX_MISSION_URL", "https://v2ex.com/mission/daily")
MAX_ATTEMPTS = int(os.getenv("V2EX_MAX_ATTEMPTS", "5"))
VOTE_ROUNDS = int(os.getenv("V2EX_VOTE_ROUNDS", "12"))

# 用来判断「导航是否真的落到首页了」。必须带上 "//"，否则 `v2ex.com` 会
# 在 edge.v2ex.com 的 URL 里也命中，等于没判断。
HOME_HOST = "//" + HOME_URL.split("://", 1)[-1].split("/", 1)[0]

# 首页侧栏的领奖入口指向 /mission/daily —— 用 href 匹配，与界面语言无关
CLAIM_ENTRY_XPATHS = ("//a[contains(@href,'/mission/daily')]",)

# 任务页「领取 X 铜币」按钮的判定方式：只认 <input type="button">（页脚「回到顶部」是
# <button type="button">，提交按钮是 type=submit，都不会被误命中），再按文案语义判断。
# ⚠️ 不要用固定选择器去「找到按钮就点、按钮没了就算成功」：领取成功后 V2EX 只是把这个
# 按钮的 value 从「领取 X 铜币」改成「查看我的账户余额」——按钮还在，文案变了。
# 领取语义的关键词集中在 is_claim_value() 里。

# 失败现场目录：captcha.png 是每次识别的原图，其余是失败时的 URL/DOM/截图
DEBUG_DIR = os.path.join(os.getcwd(), "v2ex-debug")
# 必须在任何写文件之前建好：base.py 里写 captcha.png 用的是裸 open()，
# 不会替你建父目录，目录缺失会直接 FileNotFoundError 打断整个签到。
os.makedirs(DEBUG_DIR, exist_ok=True)
img_path = os.path.join(DEBUG_DIR, "captcha.png")

# 页面上用来提示「验证码错误 / 密码错误 / 尝试次数过多」的文案节点
NOTICE_XPATHS = (
    "//*[contains(@class,'problem')]",
    "//*[contains(@class,'message')]",
    "//*[contains(@class,'error')]",
)


def get_notice_texts(driver):
    """抓页面上的提示文案（验证码错误、密码错误、限流等），诊断时最有用的一条线索。"""
    texts = []
    for xpath in NOTICE_XPATHS:
        try:
            for element in driver.find_elements(By.XPATH, xpath):
                text = (element.text or "").strip()
                if text and text not in texts:
                    texts.append(text)
        except WebDriverException:
            continue
    return texts[:10]


def _safe_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)
    except OSError as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (path, err))


def dump_debug(driver, tag, notes=(), secrets=()):
    """留存失败现场：URL、提示文案、DOM、截图。

    截图和 DOM 入库前会先清空输入框、抹掉账号密码——仓库是公开的，
    artifact 谁都能下，别顺手把凭据贴出去。
    """
    prefix = os.path.join(DEBUG_DIR, "%s_%s" % (tag, time.strftime("%H%M%S")))

    info = []
    try:
        info.append("url: %s" % driver.current_url)
        info.append("title: %s" % driver.title)
    except WebDriverException as err:
        info.append("url/title 读取失败: %s" % err)
    info.extend("notice: %s" % t for t in get_notice_texts(driver))
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


def is_logged_in(driver):
    """判断是否已进入登录态：出现登出链接，或已离开登录页且验证码框消失。"""
    try:
        if "/signout" in driver.page_source:
            return True
        if "/signin" not in driver.current_url:
            return find_visible(driver, CAPTCHA_INPUT_XPATHS)[0] is None
        return False
    except WebDriverException:
        return False


def fill_credentials(driver, username, password, timeout=15):
    """填用户名与密码。

    选择器都是语言无关的（V2EX 按 Accept-Language 换界面文案，CI 上是英文），
    用户名优先按 placeholder 匹配中英文两版，再退到「密码框之前最近的可见文本框」。
    """
    pwd = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.XPATH, "//input[@type='password']"))
    )
    pwd.clear()
    pwd.send_keys(password)

    user, xpath = find_visible(driver, USERNAME_XPATHS)
    if user is None:
        raise NoSuchElementException(
            "未找到用户名输入框（已尝试 %d 种选择器）" % len(USERNAME_XPATHS)
        )
    if xpath != USERNAME_XPATHS[0]:
        print("[INFO] 用户名输入框由兜底选择器命中: %s" % xpath)

    user.clear()
    user.send_keys(username)
    return user


def login_once(driver, username, password, attempt=1):
    """走一遍登录流程，返回是否成功。失败时留存现场。"""
    driver.get(SIGNIN_URL)
    fill_credentials(driver, username, password)

    # 等验证码图就绪。V2EX 的图是异步刷出来的，截早了会拿到空白。
    find_captcha_element(driver, timeout=15)
    time.sleep(0.5)
    code = Ocr_Captcha_Vote(driver, img_path=img_path, max_rounds=VOTE_ROUNDS)
    if not code:
        # 换图不计入登录失败次数，所以宁可不提交、整页重来，也别把存疑结果送上去
        print("===> 本轮未取得可信验证码，不提交，重新加载登录页")
        return False

    captcha_input = find_captcha_input(driver, timeout=15)
    captcha_input.clear()
    captcha_input.send_keys(code)

    submit = driver.find_element(By.XPATH, "//*[@type='submit']")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
    submit.click()
    time.sleep(3)

    if not is_logged_in(driver):
        dump_debug(
            driver,
            "a%d_login_failed" % attempt,
            notes=["识别结果: %r" % code],
            secrets=(username, password),
        )
        return False
    return True


def is_claim_value(value):
    """按钮文案是否表达「可领取」。

    领取前是「领取 X 铜币」；领取成功后 V2EX 会把它改成「查看我的账户余额」。
    所以判成功不能只看「按钮没了」，得看文案还含不含领取语义。
    """
    if not value:
        return False
    low = value.lower()
    return ("领取" in value) or ("claim" in low) or ("laim" in low)


def _visible_claim_buttons(driver):
    """当前可见、且文案仍表达「可领取」的 input[type=button]。"""
    result = []
    for element in driver.find_elements(By.XPATH, "//input[@type='button']"):
        try:
            if element.is_displayed() and is_claim_value(element.get_attribute("value")):
                result.append(element)
        except WebDriverException:
            continue
    return result


def find_claim_button(driver, timeout=15):
    """等「领取 X 铜币」按钮出现并确认它确实处于可领取状态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        buttons = _visible_claim_buttons(driver)
        if buttons:
            return buttons[0]
        time.sleep(0.3)
    return None


def _has_success_notice(driver):
    """页面是否已出现「已成功领取每日登录奖励」这类成功提示。"""
    for text in get_notice_texts(driver):
        if "成功领取" in text:
            return True
    return False


def read_balance(driver):
    """读导航栏的账户余额。

    只认 href 里的 /balance —— V2EX 按 Accept-Language 切界面语言，
    文案会跟着变（CI 上是英文），链接不会。
    返回 (展示文本, 原始 HTML)；HTML 会打进日志，万一样式改了也好照着修。
    """
    try:
        elements = driver.find_elements(By.XPATH, "//a[contains(@href,'/balance')]")
    except WebDriverException:
        return None, None

    for element in elements:
        try:
            if not element.is_displayed():
                continue
            text = " ".join((element.text or "").split())
            html = element.get_attribute("outerHTML") or ""
        except WebDriverException:
            continue
        if text or "img" in html:
            return text or None, html
    return None, None


def claim_amount(value):
    """从「领取 4 铜币」/「Claim 4 coins」这类按钮文案里抠出数额。"""
    match = re.search(r"(\d+)", value or "")
    return match.group(1) if match else ""


def notify(bot_id, status, balance, claimed="", note=""):
    """推一张飞书卡片。

    推送失败只告警，绝不因此把整次签到判成失败 —— 签到本身已经做完了。
    """
    content = ["**签到状态**: %s" % status]
    if claimed:
        content.append("**本次领取**: %s 铜币" % claimed)
    content.append("**账户余额**: %s" % (balance or "未读取到"))
    if note:
        content.append("**错误信息**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    try:
        Feishu_SendCardMsg(bot_id, " V2EX 签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def claim_daily(driver, username="", password=""):
    """签到领奖：回首页 → 点侧栏领奖入口 → 任务页点「领取 X 铜币」→ 校验结果。

    返回 (状态, 本次领取数额)，两者都会进飞书卡片。

    每一步都先等 URL 落地再查元素：page_load_strategy="none" 下 get() 立即返回，
    不等就查会查到上一个页面的 DOM（踩过：在上一个页面上点了个无关按钮还报成功）。
    """
    # 1) 回首页：既是领奖入口所在，也最直观地反映登录态
    driver.get(HOME_URL)
    wait_url(driver, HOME_HOST, 20)
    time.sleep(1)

    if "/signout" not in (driver.page_source or ""):
        dump_debug(
            driver,
            "claim_home_not_logged_in",
            notes=["首页看不到登出链接，session 可能没生效"],
            secrets=(username, password),
        )
        raise RuntimeError("首页不是登录态：url=%s" % driver.current_url)

    # 2) 首页的领奖入口只在「今天还没领」时出现，领完即消失 —— 拿它当领取状态判据
    entry, _ = wait_visible(driver, CLAIM_ENTRY_XPATHS, 15, "首页领奖入口")
    if entry is None:
        # 登录态刚确认过，所以「没有入口」= 今日已领取，不是故障。
        # 但仍留一份现场：万一是首页结构变了导致选择器失效，artifact 里能看出来。
        dump_debug(
            driver,
            "claim_entry_absent",
            notes=[
                "已确认登录态，但首页没有领奖入口，按「今日已领取」处理。"
                "若这是当天首次运行，请查本现场确认是否页面结构变了"
            ],
            secrets=(username, password),
        )
        print("===> 首页无领奖入口，判定「今日已领取」，跳过")
        return "今日已领取（跳过）", ""

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", entry)
    entry.click()
    print("===> 已点击首页的「领取今日的登录奖励」入口")
    wait_url(driver, "/mission/daily", 20)
    time.sleep(1)

    if "/signin" in (driver.current_url or ""):
        dump_debug(
            driver,
            "claim_redirected_to_signin",
            notes=["任务页被重定向回登录页，session 未在同域生效"],
            secrets=(username, password),
        )
        raise RuntimeError("任务页被重定向到登录页：url=%s" % driver.current_url)

    if "/mission/daily" not in (driver.current_url or ""):
        # 点击入口没带过去就直连任务页再试一次；还不行才是真异常。
        # 但绝不在没确认落在任务页时就去别处找按钮 —— 上一版就是拿宽选择器在错误页面上乱点。
        print("===> 点击入口后未落到任务页，改为直连 %s" % MISSION_URL)
        driver.get(MISSION_URL)
        wait_url(driver, "/mission/daily", 20)
        time.sleep(1)

        if "/signin" in (driver.current_url or "") or "/mission/daily" not in (
            driver.current_url or ""
        ):
            dump_debug(
                driver,
                "claim_not_on_mission_page",
                notes=["点击入口与直连都未能进入任务页"],
                secrets=(username, password),
            )
            raise RuntimeError("未能进入任务页：url=%s" % driver.current_url)

    # 3) 点「领取 X 铜币」
    button = find_claim_button(driver, 15)
    if button is None:
        dump_debug(
            driver,
            "claim_no_button",
            notes=["任务页没找到处于可领取状态的按钮：可能今日已领取，也可能页面结构变了"],
            secrets=(username, password),
        )
        raise RuntimeError("任务页未找到领取按钮：url=%s" % driver.current_url)

    value_before = button.get_attribute("value")
    print("===> 找到领取按钮: value=%r" % value_before)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    button.click()

    # 有的实现会弹 confirm，顺手处理掉
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        driver.switch_to.alert.accept()
        print("===> 已确认弹窗")
    except (TimeoutException, WebDriverException):
        pass

    # 4) 校验领取结果。
    # ⚠️ 领取成功后按钮**不会消失**：V2EX 把「领取 X 铜币」改成「查看我的账户余额」。
    # 判据三选一：页面出现成功提示 / 已无可领取按钮 / 文案不再表达可领取。
    deadline = time.time() + 12
    value_after = value_before
    while time.time() < deadline:
        if _has_success_notice(driver):
            print("===> 领取成功（页面提示已成功领取）")
            return "领取成功", claim_amount(value_before)

        remaining = _visible_claim_buttons(driver)
        if not remaining:
            print("===> 领取成功（已无可领取的按钮）")
            return "领取成功", claim_amount(value_before)

        value_after = remaining[0].get_attribute("value")
        time.sleep(0.5)

    dump_debug(
        driver,
        "claim_button_remained",
        notes=["点击前 value=%r，点击后 value=%r" % (value_before, value_after)],
        secrets=(username, password),
    )
    raise RuntimeError(
        "点击领取后按钮仍是可领取状态（value=%r），可能未生效；请查 artifact 里的 claim_button_remained_*"
        % value_after
    )


def v2ex(username, password, bot_id=""):
    # 空凭据是 CI 上最常见的失败原因，且跑完全流程才报错，先点出来省一轮排查
    print(
        "===> 凭据检查: username=%s password=%s"
        % (
            "已提供(%d 字符)" % len(username) if username else "**为空**",
            "已提供(%d 字符)" % len(password) if password else "**为空**",
        )
    )

    status = "签到失败"
    claimed = ""
    note = ""
    balance = None
    driver = get_web_driver()
    try:
        logged = False
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                if login_once(driver, username, password, attempt):
                    logged = True
                    break
                print("===> 第 %d 次登录未通过，换图重试" % attempt)
            except (TimeoutException, NoSuchElementException, ValueError) as err:
                print("===> 第 %d 次登录异常: %s" % (attempt, err))
                dump_debug(driver, "a%d_error" % attempt, notes=[repr(err)])
            time.sleep(2)

        if not logged:
            dump_debug(driver, "final_failure", notes=["已尝试 %d 次" % MAX_ATTEMPTS])
            raise RuntimeError("登录失败：已尝试 %d 次" % MAX_ATTEMPTS)

        print("===> v2ex 登录成功")
        status, claimed = claim_daily(driver, username, password)
        print("===> 签到结果: %s（本次领取 %s）" % (status, claimed or "-"))
    except Exception as err:
        # 失败也要推一条 —— 比只等 CI 的邮件通知直观得多
        status = "签到失败"
        note = str(err)[:200]
        raise
    finally:
        # 读余额纯粹是「锦上添花」，这里必须吞掉所有异常：
        # 在 finally 里抛出的异常会顶掉原始异常，把真正的失败原因盖掉。
        try:
            balance, html = read_balance(driver)
            if html:
                print("===> 余额元素: %s" % html[:300])
        except Exception as err:
            print("[WARN] 读取余额失败: %s" % err)
        driver.quit()
        if bot_id:
            notify(bot_id, status, balance, claimed, note)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(
            "用法: python -m Selenium.CheckIN.v2ex <用户名> <密码> [飞书机器人 webhook]"
        )
    v2ex(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
