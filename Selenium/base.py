import io

from PIL import Image
import cv2, numpy as np
import os, sys, time, ddddocr, requests, platform, traceback

from retrying import retry

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    StaleElementReferenceException,
    NoSuchElementException,
)

print("\n==== 环境检测 ====\n")


def _bypass_proxy_for_localhost():
    """把 localhost 从代理里摘出去。

    ⚠️ 本机开着代理（HTTP_PROXY/HTTPS_PROXY）又没设 NO_PROXY 时，
    Selenium 连**本机 chromedriver** 的 HTTP 请求也会被代理接管；
    代理不认识 /session/<id>/execute/... 这种路径，直接回 `unhandled request`。
    症状很阴：session 能正常建起来（browserVersion 也读得到），
    但后面每一步操作全失败 —— 看着像元素定位问题，其实是环境问题（实测 2026-10-02）。
    localhost 本来就不该走代理，这里补上；只追加、不覆盖用户已有配置。
    """
    hosts = ("localhost", "127.0.0.1", "::1")
    for key in ("NO_PROXY", "no_proxy"):
        parts = [p.strip() for p in (os.environ.get(key) or "").split(",") if p.strip()]
        lowered = [p.lower() for p in parts]
        for host in hosts:
            if host not in lowered:
                parts.append(host)
        os.environ[key] = ",".join(parts)


def get_web_driver():
    _bypass_proxy_for_localhost()
    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("window-size=1920x1080")
    options.add_argument("--disable-dev-shm-usage")
    # 打开 performance 日志：登录/回帖这类 ajax 提交的**真实响应体**要靠它抓
    # （Discuz 的成功/失败都可能不落到界面上，见 52pojie.py 的 dump_login_response）
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    # 抹掉 Selenium 的自动化指纹。V2EX 这类站点会据此判定机器人，
    # 轻则弹 Cloudflare 校验，重则把请求直接挡在验证码之前。
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    # 签到页通常包含统计、广告及长连接。导航发出后立即返回，由元素等待判断页面可用性，
    # 避免 Chrome 因站点不触发 DOMContentLoaded 而卡满默认的 300 秒。
    options.page_load_strategy = "none"
    # 本机跑时指向固定的 user-data-dir，把登录 cookie 留住。
    # 聚宽登录带风控滑块，每次冷启动都重新登录等于每天都去撞验证码；
    # 留着会话上下文就能直接跳过登录这关。CI 上不设这个变量，行为不变。
    profile_dir = os.environ.get("CHECKIN_PROFILE_DIR")
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)
        print("\n[INFO] 使用持久化浏览器 profile: %s\n" % profile_dir)
        options.add_argument("--user-data-dir=%s" % os.path.abspath(profile_dir))
    if platform.system() == "Windows":
        print("\nCurrent Operating System: ==== Windows ====\n")
        # 本机定时跑时设 CHECKIN_HEADLESS=1，免得每天弹一个浏览器窗口。
        # 默认仍有头：无头更容易被风控盯上，本地跑不差这几分钟。
        if os.environ.get("CHECKIN_HEADLESS") == "1":
            options.add_argument("--headless")
        # Selenium Manager 需要联网取 chromedriver，本机被安全策略拦住时它会被直接杀掉
        # （现象：进程 SIGTERM，什么日志都没有）。用 CHECKIN_CHROMEDRIVER 指一个现成的
        # chromedriver.exe 就能绕开，不必改代码。不设这个变量时行为不变。
        driver_path = os.environ.get("CHECKIN_CHROMEDRIVER")
        if driver_path:
            print("\n[INFO] 使用指定 chromedriver: %s\n" % driver_path)
            browser = webdriver.Chrome(
                service=Service(executable_path=driver_path), options=options
            )
        else:
            browser = webdriver.Chrome(service=service, options=options)
    elif platform.system() == "Linux":
        print("\nCurrent Operating System: ==== Linux ====\n")
        chromedriver = "/usr/bin/chromedriver"
        os.environ["webdriver.chrome.driver"] = chromedriver
        # 默认无头：CI 没桌面环境，无头不依赖 Xvfb/显示器，最稳。
        # （旧逻辑按 hostname "fv-az" 判断，新运行器名字变了会漏判，所以改成默认无头。）
        #
        # 例外：有些站点的风控（如字节 verifycenter 验证码）对**无头**特别敏感，
        # 这时可以在 xvfb-run 里跑有头模式 —— 设 CHECKIN_HEADLESS=0，并用
        # `xvfb-run -a python ...` 启动（workflow 里掘金那步就是这么跑的）。
        if os.environ.get("CHECKIN_HEADLESS") == "0":
            print("[INFO] CHECKIN_HEADLESS=0 → 有头模式（需要显示器或 xvfb-run）\n")
        else:
            options.add_argument("--headless")
        browser = webdriver.Chrome(
            service=Service(executable_path=chromedriver), options=options
        )

    # 补一刀：抹掉 navigator.webdriver。旧版 chromedriver 可能不认这条 CDP 命令，失败不影响主流程。
    try:
        browser.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            },
        )
    except WebDriverException as err:
        print("[WARN] 注入反自动化脚本失败（不影响主流程）: %s" % err)

    browser.set_page_load_timeout(45)
    browser.implicitly_wait(10)  # 所有的操作都可以最长等待10s
    return browser


def open_page(driver, url, timeout=45):
    """打开页面；慢资源超时时保留已经加载完成、可交互的 DOM。"""
    driver.set_page_load_timeout(timeout)
    try:
        driver.get(url)
    except TimeoutException as exc:
        print("[WARN] 页面加载超过 %ss，停止等待慢资源: %s" % (timeout, url))
        try:
            driver.execute_script("window.stop();")
        except WebDriverException:
            raise exc

        # 即使导航尚未提交也交给调用方的元素等待处理；部分站点会在此后才完成跳转。


def parse_cookie_header(raw):
    """把浏览器 Cookie 头解析成 [(name, value)]。

    支持直接粘 `a=1; b=2` 形式；也容忍换行分隔（有人从 DevTools 里一行一个地抄）。
    """
    pairs = []
    for chunk in (raw or "").replace("\n", ";").split(";"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        name, value = chunk.split("=", 1)
        name = name.strip()
        value = value.strip()
        if name:
            pairs.append((name, value))
    return pairs


def inject_cookies(driver, cookie_header, domain):
    """把 Cookie 注入浏览器。

    用 CDP 的 Network.setCookie：它不要求当前页面已在该域名下，也支持
    `domain=".example.com"` 这种带点前缀的写法。

    ⚠️ 只有从**真实请求头**（Network → Request Headers / Copy as cURL）里抄的 Cookie 才完整：
    站点把认证类 cookie 标了 HttpOnly，`document.cookie` / Console 读不到它们。
    """
    pairs = parse_cookie_header(cookie_header)
    if not pairs:
        raise ValueError("Cookie 为空或格式不对（应形如 name=value; name2=value2）")

    ok, failed = 0, []
    for name, value in pairs:
        try:
            driver.execute_cdp_cmd(
                "Network.setCookie",
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": "/",
                    "secure": True,
                },
            )
            ok += 1
        except WebDriverException as err:
            failed.append("%s(%s)" % (name, str(err)[:40]))
    print("===> Cookie 注入: 成功 %d 项%s" % (ok, ("，失败 " + ", ".join(failed)) if failed else ""))
    if ok == 0:
        raise RuntimeError("Cookie 一项都没注入成功")
    return ok


def checkPlatformInfo():
    arch = platform.architecture()  # 获取操作系统的位数
    print("arch=", arch)
    machine = platform.machine()  # 计算机类型
    print("machine=", machine)
    node = platform.node()  # 计算机的网络名称
    print("node=", node)
    platformIofo = platform.platform()  # 获取操作系统名称及版本号
    print("platformInfo=", platformIofo)
    processor = platform.processor()  # 计算机处理器信息
    print("processor=", processor)
    system = platform.system()
    print("system=", system)
    version = platform.version()  # 获取操作系统版本号
    print("version=", version)
    uname = platform.uname()  # 包含上面所有的信息汇总
    print("uname=", uname)


# 一直等待某元素可见，默认超时10秒（此函数暂时没有使用）
def is_visible(driver, locator, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, locator))
        )
    except TimeoutException:
        return False


# ⚠️ V2EX 按 Accept-Language 切换界面文案：中文是「用户名或电子邮件地址」/
# 「请输入上图中的验证码，点击可以更换图片」，英文是 "Username or Email" /
# "Enter the code above, click to change"。
# GitHub Actions 跑在海外 IP 上，拿到的是**英文界面** —— 只认中文 placeholder 的选择器会全部落空。
# 所以每组都配「文案选择器 + 结构化兜底」，后者靠密码框当锚点，与语言无关：
#   文档顺序为  搜索框 → 用户名 → 密码 → 验证码 → 提交
#   preceding 轴是反文档序，[1] 即密码框之前最近的那个文本框，正好落在用户名框
#   following 轴同理，[1] 落在密码框之后的验证码框
USERNAME_XPATHS = (
    "//*[@placeholder='用户名或电子邮件地址']",
    "//*[@placeholder='Username or Email']",
    "//input[@type='password']/preceding::input[@type='text' or @type='email'][1]",
)

CAPTCHA_INPUT_XPATHS = (
    "//*[@placeholder='请输入上图中的验证码，点击可以更换图片']",
    "//*[@placeholder='Enter the code above, click to change']",
    "//input[@type='password']/following::input[@type='text'][1]",
)

# 验证码图片元素的候选定位，按优先级排列：
#   1) edge.v2ex.com 新站——独立的 <img id="captcha-image" src=".../_captcha">
#   2) v2ex.com 老站——验证码是 input 自身的 inline background-image
#   3) 其余按 id/class/src 含 captcha 兜底
# 刻意不加「任意带 background-image 的元素」这种兜底：页面上的 Logo、区块阴影、
# 提交按钮都带 background-image，匹配到就是截一坨无关像素去喂 OCR，还不如直接报错。
CAPTCHA_IMG_XPATHS = (
    "//*[@id='captcha-image']",
    "//input[starts-with(@style,'background-image')]",
    "//img[contains(@src,'captcha')]",
    "//*[contains(@id,'captcha') or contains(@class,'captcha')]",
)

_ocr_cache = {}


# ddddocr 加载 onnx 模型耗时约 1~2s，按模型种类各缓存一份实例。
# 旧版（<=1.4.7）不认识 beta / show_ad 参数，逐级剔除后降级。
def _build_ocr(beta):
    candidates = [{"show_ad": False}, {}]
    if beta:
        candidates = [{"beta": True, "show_ad": False}, {"beta": True}] + candidates
    for kwargs in candidates:
        try:
            return ddddocr.DdddOcr(**kwargs)
        except TypeError:
            continue
    raise RuntimeError("ddddocr 初始化失败：没有可用的参数组合")


def get_ocr(beta=True):
    """按模型种类取 ddddocr 单例。

    加载 onnx 模型约 1~2s，所以按模型种类各缓存一份，别每次调用都新建实例。

    注意：默认模型和 beta 模型在 V2EX 验证码上**都不可靠**，各自准确率约 15%，
    没有谁明显更强（2026-09-26 采 20 张真实样本核对真值）。真正有用的是
    「两者结果一致时 2/2 全对」——所以别单独用某个模型，用 Ocr_Captcha_Vote。
    """
    key = bool(beta)
    if key not in _ocr_cache:
        _ocr_cache[key] = _build_ocr(key)
    return _ocr_cache[key]


def find_visible(driver, xpaths, min_width=0):
    """按候选 xpath 依次找第一个可见元素，返回 (element, 命中的 xpath)。

    找不到返回 (None, None)，不抛异常——调用方自己决定是重试还是报错。
    """
    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except WebDriverException:
            continue
        for element in elements:
            try:
                if element.is_displayed() and element.size["width"] >= min_width:
                    return element, xpath
            except (StaleElementReferenceException, WebDriverException):
                continue
    return None, None


def wait_url(driver, needle, timeout=20):
    """等 current_url 命中关键字，命中返回 True。

    get_web_driver() 设了 page_load_strategy="none"，driver.get() 会立刻返回，
    此刻 DOM 很可能还是上一个页面。不等 URL 落地就查元素，查到的是「上一个页面」，
    点了也白点 —— 别用宽泛的选择器掩盖这个问题。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if needle in (driver.current_url or ""):
                return True
        except WebDriverException:
            pass
        time.sleep(0.3)
    try:
        current = driver.current_url
    except WebDriverException:
        current = "(读不到)"
    print("[WARN] 等待 %ss 后 URL 仍未命中 %r，当前: %s" % (timeout, needle, current))
    return False


def wait_visible(driver, xpaths, timeout=15, label="元素"):
    """等候选 xpath 里出现可见元素，返回 (element, 命中的 xpath)；超时返回 (None, None)。

    命中兜底选择器时打日志 —— 那是「界面文案又变了」的信号，不是正常情况。
    """
    deadline = time.time() + timeout
    while True:
        element, xpath = find_visible(driver, xpaths)
        if element is not None:
            if xpath != xpaths[0]:
                print("[INFO] %s 由兜底选择器命中: %s" % (label, xpath))
            return element, xpath
        if time.time() >= deadline:
            return None, None
        time.sleep(0.3)


def find_captcha_input(driver, timeout=15):
    """等验证码输入框出现，并返回它。"""
    element, _ = wait_visible(driver, CAPTCHA_INPUT_XPATHS, timeout, "验证码输入框")
    if element is None:
        raise TimeoutException(
            "未定位到验证码输入框（已尝试 %d 种选择器，界面文案可能又变了）"
            % len(CAPTCHA_INPUT_XPATHS)
        )
    return element


def find_captcha_element(driver, timeout=10):
    """定位验证码图片元素，兼容「背景图 input」和「独立 img」两种形态。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for xpath in CAPTCHA_IMG_XPATHS:
            try:
                for element in driver.find_elements(By.XPATH, xpath):
                    size = element.size
                    if (
                        element.is_displayed()
                        and size["width"] >= 40
                        and size["height"] >= 20
                    ):
                        if xpath != CAPTCHA_IMG_XPATHS[0]:
                            print("[INFO] 验证码图由兜底选择器命中: %s" % xpath)
                        return element
            except (StaleElementReferenceException, NoSuchElementException, WebDriverException):
                continue
        time.sleep(0.3)
    raise TimeoutException("未定位到验证码图片元素（已尝试 %d 种选择器）" % len(CAPTCHA_IMG_XPATHS))


def _save_img(img_path, img_bytes):
    """留存验证码原图。

    只是排查用的副产物，写不进去也不该拖垮登录流程——目录缺失、路径非法都只告警。
    """
    if not img_path:
        return
    try:
        parent = os.path.dirname(img_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(img_path, "wb") as f:
            f.write(img_bytes)
    except OSError as err:
        print("[WARN] 保存验证码图失败 %s: %s" % (img_path, err))


def _capture_captcha(driver, locator=None):
    """取出验证码图的 element 与其 PNG 字节。优先用传入的 locator，失效则自动定位。"""
    element = None
    if locator:
        try:
            element = driver.find_element(By.XPATH, locator)
            if not element.is_displayed() or element.size["width"] < 40:
                element = None
        except (NoSuchElementException, StaleElementReferenceException, WebDriverException):
            element = None
    if element is None:
        element = find_captcha_element(driver)
    return element, element.screenshot_as_png


def Ocr_Captcha(driver, locator=None, img_path=None, beta=True):  # 验证码识别
    """截取验证码图并 OCR，返回单个模型的识别结果。

    用元素级截图（element.screenshot_as_png）取代「全屏截图 + 坐标裁剪」：
    后者在页面滚动过、或浏览器缩放档位不是 100% 时，location 与位图会错位，
    裁出来的往往是一块白底，OCR 自然识别不出。

    单模型结果不可信（准确率约 15%），实际登录请用 Ocr_Captcha_Vote。
    """
    _, img_bytes = _capture_captcha(driver, locator)
    _save_img(img_path, img_bytes)
    return get_ocr(beta).classification(img_bytes)


def _capture_changed(driver, locator, previous, tries=6):
    """取验证码位图，并保证它与 previous 不同（换图后要等新图真的到）。

    返回 (element, img_bytes, ok)。ok=False 表示连续点击后位图仍未变——
    再往下跑只会把同一张图重复识别，结果必然一样，没有意义。
    """
    element, img_bytes = _capture_captcha(driver, locator)
    if previous is None or img_bytes != previous:
        return element, img_bytes, True

    for _ in range(tries):
        try:
            element.click()
        except WebDriverException:
            pass
        time.sleep(0.8)
        element, img_bytes = _capture_captcha(driver, locator)
        if img_bytes != previous:
            return element, img_bytes, True
    return element, img_bytes, False


def Ocr_Captcha_Vote(driver, locator=None, img_path=None, max_rounds=12):
    """多轮换图，直到默认模型与 beta 模型给出一致结果才采信，返回识别文本。

    实测（2026-09-26 采 20 张真实样本核对真值）：
      - 两个模型单独用都靠不住，准确率各约 15%（`TKMGF`→`tkMcf`、`UDUOVI`→`duovi`）；
      - 但**两者结果一致时 2/2 全对** —— 一致性是可信度信号，不是准确率信号；
      - 原始一致率只有约 10%，所以轮数必须够多。换图不计入站点的登录失败次数，很划算。
    轮次用尽仍不一致时返回 None，表示「没拿到可信结果」。由调用方决定重来还是放弃，
    但**绝不把存疑结果提交上去** —— 提交错误验证码才会消耗登录失败次数。

    max_rounds=12 时，单轮拿到可信验证码的概率约 72%（1-0.9^12）。
    """
    previous = None
    for round_no in range(1, max_rounds + 1):
        element, img_bytes, ok = _capture_changed(driver, locator, previous)
        if not ok:
            print("===> 反复点击后验证码图仍未刷新，停止本轮投票")
            return None
        previous = img_bytes

        round_path = None
        if img_path:
            stem, ext = os.path.splitext(img_path)
            round_path = "%s_r%02d%s" % (stem, round_no, ext)
        _save_img(round_path or img_path, img_bytes)

        normal = get_ocr(False).classification(img_bytes)
        beta = get_ocr(True).classification(img_bytes)
        print("===> 第 %d/%d 轮识别: 默认=%r beta=%r" % (round_no, max_rounds, normal, beta))

        # 长度过短说明两个模型都识别成了碎片，即便巧合一致也不可信
        if normal and len(normal) >= 4 and normal.lower() == beta.lower():
            print("===> 两模型一致，采信: %r" % normal)
            return normal

    print("===> %d 轮均未取得一致结果，放弃本轮提交" % max_rounds)
    return None


class Track(object):
    # 处理前图片
    slider = "./slider.png"
    background = "./background.png"

    # 将处理之后的图片另存
    slider_bak = "./slider_bak.png"
    background_bak = "./background_bak.png"

    def get_track(self, slider_url, background_url) -> list:
        distance = self.get_slide_distance(slider_url, background_url)
        return self.gen_normal_track(distance)

    @staticmethod
    def gen_normal_track(distance):
        def norm_fun(x, mu, sigma):
            pdf = np.exp(-((x - mu) ** 2) / (2 * sigma**2)) / (
                sigma * np.sqrt(2 * np.pi)
            )
            return pdf

        result = []
        for i in range(-10, 10, 1):
            result.append(norm_fun(i, 0, 1) * distance)
        result.append(sum(result) - distance)
        return result

    @staticmethod
    def gen_track(distance):  # distance为传入的总距离
        # 移动轨迹
        result = []
        # 当前位移
        current = 0
        # 减速阈值
        mid = distance * 4 / 5
        # 计算间隔
        t = 0.2
        # 初速度
        v = 1

        while current < distance:
            a = 4 if current < mid else -3
            v0 = v
            # 当前速度
            v = v0 + a * t
            # 移动距离
            move = v0 * t + 1 / 2 * a * t * t
            # 当前位移
            current += move
            # 加入轨迹
            result.append(round(move))
        return result

    @staticmethod
    def onload_save_img(slider_url, slider):
        r = requests.get(slider_url)
        with open(slider, "wb") as f:
            f.write(r.content)

    def get_slide_distance(self, slider_url, background_url):
        # 下载验证码背景图,滑动图片
        self.onload_save_img(slider_url, self.slider)
        self.onload_save_img(background_url, self.background)
        # 读取进行色度图片，转换为numpy中的数组类型数据
        slider_pic = cv2.imread(self.slider, 0)
        background_pic = cv2.imread(self.background, 0)
        # 获取缺口图数组的形状 -->缺口图的宽和高
        width, height = slider_pic.shape[::-1]

        cv2.imwrite(self.background_bak, background_pic)
        cv2.imwrite(self.slider_bak, slider_pic)
        # 读取另存的滑块图
        slider_pic = cv2.imread(self.slider_bak)
        # 进行色彩转换
        slider_pic = cv2.cvtColor(slider_pic, cv2.COLOR_BGR2GRAY)
        # 获取色差的绝对值
        slider_pic = abs(255 - slider_pic)
        # 保存图片
        cv2.imwrite(self.slider_bak, slider_pic)
        # 读取滑块
        slider_pic = cv2.imread(self.slider_bak)
        # 读取背景图
        background_pic = cv2.imread(self.background_bak)
        # 比较两张图的重叠区域
        result = cv2.matchTemplate(slider_pic, background_pic, cv2.TM_CCOEFF_NORMED)
        # 获取图片的缺口位置
        top, left = np.unravel_index(result.argmax(), result.shape)
        # 背景图中的图片缺口坐标位置
        return left * 340 / 552
