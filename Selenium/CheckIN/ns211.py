# -*- coding: UTF-8 -*-
"""NS中文网（www.ns211.com）自动签到。

站点是 WordPress + ripro 主题，登录与签到**都是 admin-ajax.php 的 POST**，没有图形验证码
（页面里 `caozhuti.tencent_captcha.is` 为空 → 前端不会拉起腾讯验证码）。
所以这里只用 Selenium 点真实 UI，不做OCR / 不带 Cookie。

流程（与站点真实结构对应，均2026-10-05 实测确认）：
  1. **首页**点导航栏右上角「登录」`<div class="login-btn">` → 弹出 `#popup-signup`；
     ⚠️ 别去 `https://www.ns211.com/login` —— 那条路由的 title 是「找回密码 - NS中文网」，
     页面上既无登录按钮也无弹窗。
  2. 填 `input[name=username]` / `input[name=password]` → 点 `.go-login`；
     成功后 JS 会 `location.reload()`，所以判据是**登录态元素出现**，不是等跳转。
  3. 走签到页 `CHECKIN_URL`（= 导航「签到-QQ群 → 每日签到」指向的地址 `/7404.html`）；
     这里用直连而不是模拟两级 hover —— hover 菜单靠动画展开，CI 上容易点空。
  4. 点侧栏的签到按钮拿回执；**点不到就直接调 `user_qiandao` 接口**（见 ajax_qiandao
     的注释，那段是首跑失败后加的兜底，也是最可靠的一条路）。

⚠️ 签到按钮的类名有坑，且**不要只依赖 UI 点击**：
  - 侧栏用户卡片里的按钮是 `.btn-qiandao`（CSS 给了圆角胶囊样式，与截图一致）；
  - 全站唯一绑点击事件的是 `$(".click-qiandao")`，而它所在的 `.rollbar` 悬浮条
    在 app.css 里是 `display: none` —— 不可见也不可点；
  - `.btn-qiandao` 在 app.js 里出现 0 次，是否也挂了 `click-qiandao` 类无法在
    未登录状态下确认。所以脚本**先点 UI，12s 内拿不到回执就直接调接口**。

⚠️ 关于「签到」按钮的选择器（踩过的坑，别改回简单写法）：
站点上 `class="click-qiandao"` 有**两处**——右下角悬浮条（rollbar）和侧栏用户卡片。
未登录时悬浮条那个也在！所以：
  - 优先在 `sidebar-column` 容器里找 —— 悬浮条不在侧栏里，不会误命中；
  - 找不到再退回全页面找，此时必须先确认已登录，否则点到的是悬浮条那个；
  - **不能只判「找到 click-qiandao 就点」**：点悬浮条那个在未登录时只会弹登录框，
    看起来像「点了但没反应」。

签到结果判定：
`.click-qiandao` 成功后 JS 会弹 SweetAlert2 再 `location.reload()`，reload 后按钮文案会变
（已签到不再是「签到」）。所以判成功看三者任一：
  - 弹出成功类文案（成功/已签到/重复签到…）；
  - reload 后侧栏积分比点击前涨了；
  - 侧栏签到按钮不再表达「可签到」。
任何无法归类的情况都 dump 现场后抛错 —— 绝不打日志就算成功。

用法：
    python -m Selenium.CheckIN.ns211 <用户名> <密码> [飞书机器人 webhook]
    # 或走环境变量（推荐，与 52pojie / 掘金一致）：
    NS211_USERNAME=xxx NS211_SECRET=xxx python -m Selenium.CheckIN.ns211

⚠️ Secret 叫 `NS211_SECRET`（不是 PASSWORD），环境变量两套拼写都认：
    NS211_SECRET / NS211_PASSWORD（仓库里的真实名字是前者）

可选环境变量：
    NS211_HOME_URL      首页（登录入口所在页），默认 https://www.ns211.com/
    NS211_CHECKIN_URL   签到页，默认 https://www.ns211.com/7404.html
                        （= 导航「签到-QQ群 → 每日签到」指向的地址）
    NS211_LOGIN_RETRIES 登录重试次数，默认 3
    FEISHU_BOT_ID       飞书机器人 webhook，给了才推卡片

失败现场写进 ns211-debug/，CI 里由 workflow 收集成 artifact。
"""

import os
import re
import sys
import time

from Selenium.base import *

HOME_URL = os.getenv("NS211_HOME_URL", "https://www.ns211.com/")
CHECKIN_URL = os.getenv("NS211_CHECKIN_URL", "https://www.ns211.com/7404.html")
LOGIN_RETRIES = int(os.getenv("NS211_LOGIN_RETRIES", "3"))

HOST = "ns211.com"

DEBUG_DIR = os.path.join(os.getcwd(), "ns211-debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

#登录表单的最终落点：ripro 的 open_signup_popup() 会把 #popup-signup 的 HTML
# **搬进 SweetAlert2**（Swal.fire({html: ...})），#popup-signup 自己永远 display:none。
# 所以判据必须看 .swal2-container 里有没有表单，不能等 #popup-signup 可见（那永远等不到）。
LOGIN_FORM_XPATHS = (
    "//div[contains(@class,'swal2-container')]//input[@name='username']",
    "//div[contains(@class,'swal2-popup')]//input[@name='username']",
    "//input[@name='username']",
)
LOGIN_PASS_XPATHS = (
    "//div[contains(@class,'swal2-container')]//input[@name='password']",
    "//input[@type='password']",
)
LOGIN_BTN_XPATHS = (
    "//button[contains(@class,'go-login')]",
    "//a[contains(@class,'go-login')]",
)

# 导航栏的登录入口。⚠️ 它是 **`<div class="login-btn navbar-button">`，不是 `<a>`**
# （2026-10-05 实测；本机第一版写成 //a[...] 直接漏掉，报「未找到登录入口」）。
# 而且**必须从首页进**——`https://www.ns211.com/login` 这条路由的title 是「找回密码 - NS中文网」，
# 页面上既没有登录按钮也没有登录弹窗，别拿它当登录页。
OPEN_LOGIN_XPATHS = (
    "//div[contains(@class,'login-btn')]",
    "//*[contains(@class,'login-btn')]",
    "//*[@id='login']//button[contains(@class,'go-login')]/ancestor::*[contains(@class,'popup')]",
)

# 登录成功的判据：ripro 主题登录后导航栏 `.login-btn` 被替换成用户菜单，
# 同时侧栏会出现用户卡片（含「签到」按钮）。这里优先认「导航里的用户链接」。
# 不用「URL 变化」判断——站点是 location.reload()，URL 压根不变。
LOGGED_IN_XPATHS = (
    "//div[contains(@class,'actions')]//a[contains(@href,'/user')]",
    "//div[contains(@class,'actions')]//a[contains(@href,'?action=')]",
    "//div[contains(@class,'user-info')]//a",
    "//a[contains(@href,'action=logout')]",
    "//span[contains(@class,'user-name')]",
)

# 登录/签到失败时站点用 SweetAlert2 弹提示，这些是它的容器类名。
SWAL_XPATHS = (
    "//div[contains(@class,'swal2-popup')]",
    "//div[contains(@class,'swal2-content')]",
)

# 签到按钮的定位（2026-10-05 CI 首跑失败后取证修正，见下方注释）。
#
# ⚠⚠ 三个互相独立的坑，任一没踩对都会得到「找不到签到按钮」——
#
# 1. **真实类名是 `btn-qiandao`，不是 `click-qiandao`。**
#    `click-qiandao` 只存在于右下角悬浮条 `.rollbar` 里，而 app.css 里
#    `.rollbar { display: none }` —— 悬浮条默认**不可见**，
#    于是 find_visible() 的 is_displayed() 全落空，页面上等于没有这个按钮。
#    真正能点的是侧栏用户卡片 `.widget-userinfo` 里的 `.btn-qiandao`
#    （CSS 明确给了它按钮样式：圆角胶囊 + #f2f7ff 底色 + .75rem 字号，
#    与用户截图里侧栏那个蓝色「签到」按钮一致）。
#
# 2. 因此**别用 click-qiandao 当兜底** —— 它即使存在也不可点。
#    兜底改成「widget-userinfo 内的可见签到元素」与「文本为签到的可见元素」。
#
# 3. 判定文本时用 `contains`（normalize-space()='签到'）会漏掉按钮里的 <i> 图标等
#    混合节点，故用 `contains(normalize-space(),'签到')`。
CHECKIN_BTN_XPATHS = (
    # 主路径：侧栏用户卡片里的签到按钮
    "//div[contains(@class,'widget-userinfo')]//*[contains(@class,'btn-qiandao')]",
    "//div[contains(@class,'widget-userinfo')]//*[contains(@class,'qiandao')]",
    # 次路径：任意位置的 btn-qiandao
    "//*[contains(@class,'btn-qiandao')]",
    # 兜底：侧栏里文本为「签到」的可见元素
    "//div[contains(@class,'widget-userinfo')]//*[contains(normalize-space(),'签到')]",
    "//div[contains(@class,'sidebar')]//a[contains(normalize-space(),'签到')]",
    # 最后兜底：全页面文本为「签到」的可见元素（不含 click-qiandao，那货不可见）
    "//a[contains(normalize-space(),'签到')]",
)

# 站点提示里表示「签到成功/已完成」的措辞。
SUCCESS_HINTS = ("签到成功", "今日已签到", "已经签到", "已签到", "重复签到", "明天再来")
# 明确表示失败的措辞 —— 出现这些一律判失败，不许被「成功」误吞。
FAIL_HINTS = ("失败", "错误", "未登录", "请先登录", "登录已过期", "异常", "禁止")

# 站点未登录时会弹这个，签到没生效时最常见的原因。
NOT_LOGGED_HINTS = ("请先登录", "未登录", "登录已过期")


def _safe_write(path, data):
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w", encoding=None if isinstance(data, bytes) else "utf-8") as f:
            f.write(data)
    except OSError as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (path, err))


def get_popup_texts(driver):
    """抓 SweetAlert2 弹窗里的文案（站点所有成功/失败提示都走它）。"""
    texts = []
    for xpath in SWAL_XPATHS:
        try:
            for element in driver.find_elements(By.XPATH, xpath):
                text = " ".join((element.text or "").split())
                if text and text not in texts:
                    texts.append(text)
        except WebDriverException:
            continue
    return texts


def dump_debug(driver, tag, notes=(), secrets=()):
    """留存失败现场：URL、弹窗文案、DOM、截图。

    DOM/截图入库前清空输入框并抹掉凭据 —— 仓库是公开的，artifact 谁都能下。
    """
    prefix = os.path.join(DEBUG_DIR, "%s_%s" % (tag, time.strftime("%H%M%S")))

    info = []
    for getter, label in ((lambda: driver.current_url, "url"), (lambda: driver.title, "title")):
        try:
            info.append("%s: %s" % (label, getter()))
        except WebDriverException as err:
            info.append("%s 读取失败: %s" % (label, err))
    info.extend("popup: %s" % t for t in get_popup_texts(driver))
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
    """是否已处于登录态：导航栏不再有「登录」div，且出现了用户菜单节点。"""
    try:
        has_login_entry = bool(
            driver.find_elements(By.XPATH, "//div[contains(@class,'login-btn')]")
        )
    except WebDriverException:
        return False
    if has_login_entry:
        return False
    _, xpath = find_visible(driver, LOGGED_IN_XPATHS)
    if xpath:
        print("===> 登录态由 %s 确认" % xpath)
        return True
    # 兜底：登录弹窗还开着 = 没登录成
    try:
        popup = driver.find_element(By.ID, "popup-signup")
        if popup.is_displayed():
            return False
    except (NoSuchElementException, StaleElementReferenceException, WebDriverException):
        pass
    return True


def open_login_popup(driver, timeout=20):
    """点导航栏「登录」，把登录表单拉出来。

    ⚠️ 这里的坑（本机实测两次才摸对）：
      1. 入口是 `<div class="login-btn navbar-button">`，不是 `<a>`；
      2. 它在**首页**，不在 /login（那条路由是找回密码页）；
      3. `.login-btn` 的点击绑定在 app.js 的 `signup_popup()` 里，等jQuery ready 才挂上。
         base.py 用了 `page_load_strategy="none"`，导航一返回 DOM 可能还没绑好，
         这时候点一下毫无反应 —— 所以**反复点，直到表单真的出现**，而不是点一次就等。
      4. 点开后表单在 SweetAlert2 里（`#popup-signup` 始终 display:none），
         所以判据是「`.swal2-container` 里有 input[name=username]」。
    """
    deadline = time.time() + timeout
    clicks = 0
    while time.time() < deadline:
        if find_visible(driver, LOGIN_FORM_XPATHS)[0] is not None:
            print("===> 登录表单已就位（点%d 次）" % clicks)
            return

        entry, xpath = find_visible(driver, OPEN_LOGIN_XPATHS)
        if entry is None:
            raise TimeoutException(
                "未找到登录入口（已尝试 %d 种选择器）" % len(OPEN_LOGIN_XPATHS)
            )
        try:
            entry.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", entry)
        clicks += 1
        print("===> 已点击登录入口（%s）第 %d 次" % (xpath, clicks))
        # SweetAlert2 渲染需要点时间；渲染完成前 login 字段还不存在
        time.sleep(1.2)

    if find_visible(driver, LOGIN_FORM_XPATHS)[0] is not None:
        return
    dump_debug(driver, "login_popup_timeout", notes=["点了 %d 次仍无登录表单" % clicks])
    raise TimeoutException("点击登录入口 %d 次后登录表单仍未出现" % clicks)


def fill_login_form(driver, username, password, timeout=15):
    """填用户名密码。定位不到就抛异常，绝不带着空表单去点登录。"""
    user, uxpath = wait_visible(driver, LOGIN_FORM_XPATHS, timeout, "用户名输入框")
    if user is None:
        raise NoSuchElementException(
            "未找到用户名输入框（已尝试 %d 种选择器）" % len(LOGIN_FORM_XPATHS)
        )
    pwd, pxpath = wait_visible(driver, LOGIN_PASS_XPATHS, timeout, "密码输入框")
    if pwd is None:
        raise NoSuchElementException(
            "未找到密码输入框（已尝试 %d 种选择器）" % len(LOGIN_PASS_XPATHS)
        )
    if uxpath != LOGIN_FORM_XPATHS[0] or pxpath != LOGIN_PASS_XPATHS[0]:
        print("[INFO] 登录表单由兜底选择器命中: %s / %s" % (uxpath, pxpath))

    user.clear()
    user.send_keys(username)
    pwd.clear()
    pwd.send_keys(password)


def login_once(driver, username, password, attempt=1):
    """走一遍登录流程。返回是否成功；失败时留存现场。

    从**首页**进（不是 /login —— 那条路由是找回密码页），点导航栏右上角
    `<div class="login-btn">` 把#popup-signup 弹窗拉起来。
    """
    open_page(driver, HOME_URL)
    wait_url(driver, HOST, 20)
    time.sleep(1)

    open_login_popup(driver)
    fill_login_form(driver, username, password)

    btn, bxpath = wait_visible(driver, LOGIN_BTN_XPATHS, 10, "安全登录按钮")
    if btn is None:
        dump_debug(driver, "a%d_no_login_btn" % attempt, secrets=(username, password))
        raise NoSuchElementException("未找到「安全登录」按钮")

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    btn.click()
    print("===> 已点击安全登录（%s），等待登录结果" % bxpath)

    # 成功后站点是 location.reload()（URL 不变），所以只能等登录态元素出现。
    # 失败时 SweetAlert2 会弹出提示文案，一并抓出来当线索。
    deadline = time.time() + 20
    while time.time() < deadline:
        popups = get_popup_texts(driver)
        if is_logged_in(driver):
            print("===> 登录成功")
            return True
        if any(h in p for p in popups for h in FAIL_HINTS):
            print("===> 站点提示登录失败: %s" % " | ".join(popups))
            break
        time.sleep(0.5)

    dump_debug(
        driver,
        "a%d_login_failed" % attempt,
        notes=["已尝试 %d 次" % attempt],
        secrets=(username, password),
    )
    return False


def read_points(driver):
    """读侧栏的积分余额，返回字符串或 None。

    只认 `widget-userinfo` 用户卡片里的数字 —— 页面正文（签到规则说明）里也有
    「签到…可得1积分」「积分超过3…」这类字样，早先版本用全页`//*[contains(text(),'积分')]`
    会抓到规则说明里的数字，把「签到前积分」读成300这种假数。
    抓不到只影响通知内容，不影响签到结论。
    """
    patterns = (
        "//div[contains(@class,'widget-userinfo')]//*[contains(@class,'num')]",
        "//div[contains(@class,'widget-userinfo')]//*[contains(@class,'author-fields')]",
    )
    for xpath in patterns:
        try:
            for element in driver.find_elements(By.XPATH, xpath):
                if not element.is_displayed():
                    continue
                text = " ".join((element.text or "").split())
                if text:
                    match = re.search(r"(\d+(?:\.\d+)?)", text)
                    if match:
                        print("===> 积分读数: %s（来自 %s）" % (match.group(1), xpath))
                        return match.group(1)
        except (StaleElementReferenceException, WebDriverException):
            continue
    print("[WARN] 未读到积分")
    return None


def _button_state(driver, xpaths):
    """签到按钮当前的可见性与文案，用于判定「点完有没有变」。"""
    element, xpath = find_visible(driver, xpaths)
    if element is None:
        return None, "", None
    try:
        text = " ".join((element.text or "").split())
        disabled = element.get_attribute("disabled")
        cls = element.get_attribute("class") or ""
    except (StaleElementReferenceException, WebDriverException):
        return element, "", None
    return element, text, (disabled, cls, xpath)


def _classify_popup(texts):
    """按站点提示文案分类签到结果，返回 (状态, 是否成功)。"""
    joined = " | ".join(texts)
    if not joined.strip():
        return "", None
    for hint in FAIL_HINTS:
        if hint in joined:
            return joined, False
    for hint in SUCCESS_HINTS:
        if hint in joined:
            return joined, True
    return joined, None


def ajax_qiandao(driver, timeout=20):
    """直接调站点的 `user_qiandao` 接口，返回解析后的 (msg, status)。

    为什么必须有这条兜底（2026-10-05 CI 首跑教训）：
      - 页面 JS 只把点击事件绑在 `.click-qiandao` 上（app.js 全文仅此一处）；
      - 那个类所在的 `.rollbar` 悬浮条在 app.css 里是 `display: none`，**不可点**；
      - 侧栏用户卡片里真正的按钮是 `.btn-qiandao`，**app.js 里出现 0 次**，
        很可能没绑事件（也可能两个类同时挂上，本机无登录态 DOM 没法确认）。
      与其赌按钮类名，不如直接打接口 —— 站点自己的回执才是权威判据。
    接口在 app.js 里就是这么调的：`$.post(caozhuti.ajaxurl, {action: "user_qiandao"})`，
    返回 `{status: 1, msg: "..."}`。这里用同步 XHR 拿返回体，比抓 SweetAlert2 可靠。
    """
    script = """
    var xhr = new XMLHttpRequest();
    xhr.open('POST', caozhuti.ajaxurl, false);   // 同步：等回执再返回
    xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded; charset=UTF-8');
    xhr.send('action=user_qiandao');
    return xhr.responseText;
    """
    try:
        raw = driver.execute_script(script)
    except WebDriverException as err:
        print("[WARN] 调user_qiandao 接口异常: %s" % err)
        return "", None
    if not raw:
        return "", None
    print("===> user_qiandao 接口返回: %s" % str(raw)[:300])
    try:
        import json

        data = json.loads(raw)
        return str(data.get("msg", "")), data.get("status")
    except (ValueError, AttributeError) as err:
        print("[WARN] 解析接口返回失败 %s: %r" % (err, str(raw)[:200]))
        return str(raw)[:200], None


def _verdict_from_status(msg, status):
    """按接口的 status/msg 判定成功与否。"""
    text = msg or ""
    if status is not None:
        # 站点约定 status==1 为成功（app.js: `1 == a.status ? 成功 : 提示`）
        try:
            if int(status) == 1:
                return text or "签到成功", True
            return text or "站点返回 status=%s" % status, False
        except (TypeError, ValueError):
            pass
    if not text:
        return "", None
    return _classify_popup([text])


def do_checkin(driver, username="", password=""):
    """签到：导航到签到页 → 点侧栏「签到」→ 拿站点回执判定。

    返回 (状态文案, 成功与否, 回执原文)。
    """
    # 直接走签到页。导航栏「签到-QQ群 → 每日签到」指向的就是这个 URL，
    # 直接 get 比模拟两级 hover 稳（hover 菜单依赖动画，CI 上容易点空）。
    open_page(driver, CHECKIN_URL)
    wait_url(driver, HOST, 20)
    time.sleep(1.5)

    if not is_logged_in(driver):
        dump_debug(
            driver,
            "checkin_not_logged_in",
            notes=["签到页仍是未登录态， session 没生效"],
            secrets=(username, password),
        )
        raise RuntimeError("签到页不是登录态：url=%s" % driver.current_url)

    points_before = read_points(driver)

    # 优先走真实 UI：点按钮，让站点自己的 JS 发请求
    element, xpath = wait_visible(driver, CHECKIN_BTN_XPATHS, 10, "签到按钮")
    text_before = ""
    if element is not None:
        try:
            text_before = " ".join((element.text or "").split())
        except (StaleElementReferenceException, WebDriverException):
            pass
        print("===> 命中签到按钮（%s），文案=%r" % (xpath, text_before))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except WebDriverException:
            driver.execute_script("arguments[0].click();", element)
        print("===> 已点击签到按钮，等待站点回执")
    else:
        print("===> 未找到可点的签到按钮，直接走接口兜底")

    # 站点成功后会location.reload()：URL 不变，所以只能靠「弹窗文案」和
    # 「按钮/积分状态变化」两条判据。
    deadline = time.time() + 12
    popup_raw = ""
    while time.time() < deadline:
        texts = get_popup_texts(driver)
        popup_raw, verdict = _classify_popup(texts)
        if verdict is False:
            print("===> 站点明确回报失败: %s" % popup_raw)
            return popup_raw, False, popup_raw
        if verdict is True:
            print("===> 站点回报成功: %s" % popup_raw)
            return popup_raw, True, popup_raw

        element_now, text_after, _ = _button_state(driver, CHECKIN_BTN_XPATHS)
        if text_before and text_after and text_after != text_before:
            print("===> 按钮文案已变化 %r → %r，判定签到成功" % (text_before, text_after))
            return text_after, True, popup_raw

        time.sleep(0.6)

    # UI 那条路没拿到回执 → 直接调接口。站点自己的返回才是权威判据。
    print("===> UI 未取得回执，改调 user_qiandao 接口")
    msg, status = ajax_qiandao(driver)
    text, verdict = _verdict_from_status(msg, status)
    if verdict is not None:
        points_after = read_points(driver)
        if verdict and points_before and points_after and points_after != points_before:
            text = "%s（积分 %s → %s）" % (text, points_before, points_after)
        print("===> 接口判定: %s（成功=%s）" % (text, verdict))
        return text, verdict, msg or popup_raw

    dump_debug(
        driver,
        "checkin_no_verdict",
        notes=[
            "点击 + 直接调接口都没拿到成功/失败回执。",
            "点击前按钮: %r" % (text_before,),
            "点击后按钮: %r" % (_button_state(driver, CHECKIN_BTN_XPATHS)[1],),
            "接口返回: msg=%r status=%r" % (msg, status),
        ],
        secrets=(username, password),
    )
    return "点击后未取得站点回执（UI 与接口均无返回）", False, msg or popup_raw


def notify(bot_id, status, points, note=""):
    """推一张飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append("**当前积分**: %s" % (points or "未读取到"))
    if note:
        content.append("**站点回执**: %s" % note[:300])
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        from Messaging.Feishu import Feishu_SendCardMsg

        Feishu_SendCardMsg(bot_id, " NS中文网签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """凭据优先取环境变量，命令行参数兜底。

    ⚠️ Secret 名字是 NS211_SECRET；NS211_PASSWORD 只是同名兼容，别只认一种拼写。
    """
    username = os.getenv("NS211_USERNAME") or (argv[1] if len(argv) > 1 else "")
    password = (
        os.getenv("NS211_SECRET")
        or os.getenv("NS211_PASSWORD")
        or (argv[2] if len(argv) > 2 else "")
    )
    bot_id = os.getenv("FEISHU_BOT_ID") or (argv[3] if len(argv) > 3 else "")
    return username, password, bot_id


def ns211():
    username, password, bot_id = resolve_credentials(sys.argv)

    print(
        "===> 凭据检查: username=%s password=%s"
        % (
            "已提供(%d 字符)" % len(username) if username else "**为空**",
            "已提供(%d 字符)" % len(password) if password else "**为空**",
        )
    )
    if not username or not password:
        sys.exit(
            "缺少 NS211 凭据。需要环境变量 NS211_USERNAME + NS211_SECRET（或 NS211_PASSWORD），"
            "或命令行参数 <用户名> <密码>。"
        )

    status = "签到失败"
    success = False
    note = ""
    points = None
    driver = get_web_driver()
    try:
        logged = False
        for attempt in range(1, LOGIN_RETRIES + 1):
            try:
                if login_once(driver, username, password, attempt):
                    logged = True
                    break
                print("===> 第 %d 次登录未通过，重试" % attempt)
            except (TimeoutException, NoSuchElementException, WebDriverException) as err:
                print("===> 第 %d 次登录异常: %s" % (attempt, err))
                dump_debug(driver, "a%d_error" % attempt, notes=[repr(err)], secrets=(username, password))
            time.sleep(2)

        if not logged:
            dump_debug(driver, "final_login_failure", notes=["已尝试 %d 次" % LOGIN_RETRIES])
            raise RuntimeError("登录失败：已尝试 %d 次" % LOGIN_RETRIES)

        print("===> 登录成功，开始签到")
        status, success, note = do_checkin(driver, username, password)
        print("===> 签到结果: %s" % status)

        # 读完积分/回到签到页拿最终状态。纯锦上添花，必须吞掉所有异常。
        try:
            points = read_points(driver)
        except Exception as err:
            print("[WARN] 读取积分失败: %s" % err)

        if not success:
            raise RuntimeError("签到未成功：%s" % status)
    except Exception as err:
        status = "签到失败"
        note = str(err)[:300]
        print("===> ns211 失败: %s" % err)
        return 1
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        if bot_id:
            notify(bot_id, status, points, note)

    return 0


if __name__ == "__main__":
    sys.exit(ns211())