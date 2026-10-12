# -*- coding: UTF-8 -*-
"""v2ex.py 的离线回归测试：只验判定逻辑，不开浏览器。

2026-10-11/12 连续两天签到失败，根因是 V2EX 首页返回 Cloudflare 的 HTTP ERROR 522，
而旧流程把「错误页」当成「没登录」，一票否决。这里锁住的是修复后的三个判定：
  1. error_hint()      —— 认得出 522/502/nginx 错误页，且不误伤正常页
  2. is_logged_in()    —— 错误页不能被判成「已登录」
  3. has_claimed_text() —— 中英文的「今日已领取」都认得

依赖注入说明：`Selenium.base` 会 import cv2 / ddddocr / numpy 这些在本机和 CI 上都不一定
齐的重包，直接 import 会失败。所以这里把 Selenium.base 和 Messaging.Feishu 换成假的，
只给 v2ex.py 实际用到的那几个名字，被测的仍然是 v2ex.py 的真实源码。

跑法（仓库根目录）：
    python Selenium/CheckIN/v2ex_error_page_test.py
"""

import os
import sys
import types
import unittest

# 保证能从任意目录跑：把仓库根塞进 sys.path，才能 import Selenium.CheckIN.v2ex
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --------------------------------------------------------------------------
# 假依赖：只提供 v2ex.py 用到的符号
# --------------------------------------------------------------------------
class FakeException(Exception):
    pass


import time as _real_time  # noqa: E402


class _FakeTime(object):
    """把 sleep 变成 no-op（测试里没有真浏览器要等），其余照旧。

    ⚠️ time.time() 必须走真实时钟：find_claim_button 拿它算 deadline，
    返回一个常量会让 `while time.time() < deadline` 在找不到按钮时死循环。
    """

    slept = []

    @staticmethod
    def sleep(seconds):
        _FakeTime.slept.append(seconds)

    @staticmethod
    def time():
        # sleep 不再真等，但 time() 必须照样往前进 —— 基于 deadline 的等待循环
        # （find_claim_button 那种）要么死循环（时钟不动），要么白等满 15 秒（真时钟）。
        return _real_time.time() + sum(_FakeTime.slept)

    @staticmethod
    def strftime(fmt, *args):
        return _real_time.strftime(fmt, *args)


def _install_fakes():
    base = types.ModuleType("Selenium.base")
    base.By = types.SimpleNamespace(XPATH="xpath")
    base.EC = types.SimpleNamespace(alert_is_present=lambda: None)
    class _WaitResult(object):
        def __init__(self, *args, **kwargs):
            pass

        def until(self, _condition):
            # 没有 alert 弹窗，按「超时」处理 —— v2ex.py 里已捕获 TimeoutException
            raise base.TimeoutException("no alert")

    base.WebDriverWait = _WaitResult
    base.WebDriverException = FakeException
    base.TimeoutException = FakeException
    base.NoSuchElementException = FakeException
    base.CAPTCHA_INPUT_XPATHS = ("//fake-captcha",)
    base.time = _FakeTime

    # v2ex.py 流程里会调用的几个（本测试只会走到纯逻辑分支，给个桩即可）
    base.wait_url = lambda *a, **k: True
    base.wait_visible = lambda *a, **k: (None, None)
    base.find_visible = lambda *a, **k: (None, None)
    base.find_captcha_element = lambda *a, **k: None
    base.find_captcha_input = lambda *a, **k: None
    base.Ocr_Captcha_Vote = lambda *a, **k: None
    base.get_web_driver = lambda: None

    pkg = types.ModuleType("Selenium")
    pkg.__path__ = []
    pkg.base = base
    sub = types.ModuleType("Selenium.CheckIN")
    sub.__path__ = []

    feishu = types.ModuleType("Messaging.Feishu")
    feishu.Feishu_SendCardMsg = lambda *a, **k: None
    msgs = types.ModuleType("Messaging")
    msgs.__path__ = []
    msgs.Feishu = feishu

    for name, module in (
        ("Selenium", pkg),
        ("Selenium.base", base),
        ("Selenium.CheckIN", sub),
        ("Messaging", msgs),
        ("Messaging.Feishu", feishu),
    ):
        sys.modules.setdefault(name, module)


_install_fakes()

import importlib.util  # noqa: E402
import tempfile  # noqa: E402

# v2ex.py 顶层会按 cwd 建 v2ex-debug/ 目录；先躲到临时目录里加载，跑完不留下垃圾
_HERE = os.path.dirname(os.path.abspath(__file__))
_CWD = os.getcwd()
_TMP = tempfile.mkdtemp(prefix="v2ex_test_")
os.chdir(_TMP)
try:
    _spec = importlib.util.spec_from_file_location(
        "v2ex_under_test", os.path.join(_HERE, "v2ex.py")
    )
    v2ex = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(v2ex)
finally:
    os.chdir(_CWD)


# --------------------------------------------------------------------------
# 素材：贴的是 CI artifact 里那张 522 页面的真实文本
# --------------------------------------------------------------------------
ERROR_522 = """<html><head><title>v2ex.com</title></head><body>
This page isn&#8217;t working
If the problem continues, contact the site owner.
HTTP ERROR 522
Reload
</body></html>"""

ERROR_NGINX = """<html><head><title>502 Bad Gateway</title></head>
<body><center><h1>502 Bad Gateway</h1></center><hr><center>nginx</center></body></html>"""

CLOUDFLARE_BLOCK = """<html><head><title>Attention Required! | Cloudflare</title></head>
<body>Sorry, you have been blocked. Cloudflare Ray ID: 8a9b</body></html>"""

HOME_LOGGED_IN = (
    "<html><body><div id='Top'><a href='/signout'>登出</a>"
    "<a href='/balance'>1,234</a></div>"
    + "<div class='box'>" * 50
    + "</body></html>"
)

# 登录页：短，但它是真页面 —— 不能因为短就被判成错误页
SIGNIN_PAGE = (
    "<html><body><form action='/signin'><input type='password'>"
    "<input type='text' placeholder='Enter the code above, click to change'>"
    "<div id='captcha'></div></form></body></html>"
)

# 真实任务页是这个量级（有完整 head / 导航栏 / 页脚），别把素材裁得太瘦 ——
# 顺带验证「页面过短」这条判据不会误伤正文页
_PAGE_FILLER = "<div class='cell'>v2ex node</div>" * 60

MISSION_CLAIMED_CN = (
    "<html><head><title>V2EX › 任务</title></head><body>"
    "<div id='Wrapper'><div>已成功领取每日登录奖励</div>"
    "<div>已连续登录 3 天</div>"
    "<input type='button' value='查看我的账户余额'>"
    + _PAGE_FILLER
    + "</div></body></html>"
)

MISSION_CLAIMED_EN = (
    "<html><head><title>V2EX › Mission</title></head><body>"
    "<div>You have received your daily login bonus.</div>"
    "<div>Logged in for 3 consecutive days</div>"
    + _PAGE_FILLER
    + "</body></html>"
)

MISSION_CLAIMABLE = (
    "<html><body><input type='button' value='领取 4 铜币'>"
    + "<div class='box'>v2ex mission</div>" * 80
    + "</body></html>"
)

_HOME = v2ex.HOME_URL
_MISSION = v2ex.MISSION_URL


class FakeDriver(object):
    """只需要 page_source 和 current_url 的最小 driver。"""

    def __init__(self, source, url="https://v2ex.com/"):
        self.page_source = source
        self.current_url = url
        self.title = "v2ex"


class FakeEl(object):
    """最小 WebElement：只有 is_displayed / get_attribute / text / click 有用。"""

    def __init__(self, value=None, text="", on_click=None):
        self._value = value
        self._text = text
        self._on_click = on_click
        self.size = {"width": 100, "height": 30}

    def is_displayed(self):
        return True

    def get_attribute(self, name):
        return self._value if name == "value" else None

    @property
    def text(self):
        return self._text

    def click(self):
        if self._on_click:
            self._on_click()


class ScriptedDriver(object):
    """按 current_url 返回预设页面的假 driver，用来跑 claim_daily 的完整分支。"""

    def __init__(self, pages, claim_value="领取 4 铜币"):
        self.pages = pages
        self.claim_value = claim_value  # None = 页面上没有可领取按钮
        self.url = None
        self.title = "v2ex"
        self.claimed = False
        self.nav_log = []

    def get(self, url):
        self.nav_log.append(url)
        self.url = url

    @property
    def current_url(self):
        return self.url or ""

    @property
    def page_source(self):
        source = self.pages.get(self.url)
        if source is not None:
            return source
        for key, value in self.pages.items():
            if key and key in (self.url or ""):
                return value
        return ""

    def find_elements(self, by, xpath):
        if xpath == "//input[@type='button']":
            # 领取成功后 V2EX 把按钮文案改成「查看我的账户余额」，不再是可领取状态
            if self.claimed or self.claim_value is None:
                return []
            if "mission/daily" in (self.url or ""):
                return [FakeEl(self.claim_value, on_click=self._claim)]
            return []
        if xpath.startswith("//*[contains(@class"):
            if self.claimed:
                return [FakeEl(text="已成功领取每日登录奖励")]
            return []
        return []

    def _claim(self):
        self.claimed = True

    def execute_script(self, *args, **kwargs):
        return None

    def get_screenshot_as_png(self):
        return b""

    def quit(self):
        return None


class ClaimFlowTest(unittest.TestCase):
    """核心回归：站点抽风时签到必须还能成。

    2026-10-11/12 的现场就是 —— 登录成功了，首页返回 522，旧代码当场判失败。
    """

    def test_home_522_falls_back_to_direct_mission(self):
        driver = ScriptedDriver({_HOME: ERROR_522, _MISSION: MISSION_CLAIMABLE})
        status, amount = v2ex.claim_daily(driver)

        self.assertEqual("领取成功", status)
        self.assertEqual("4", amount)
        self.assertIn(_MISSION, driver.nav_log, "首页挂了必须直连任务页")
        print("首页 522 →", status, "| 导航:", driver.nav_log)

    def test_home_ok_without_entry_is_already_claimed(self):
        driver = ScriptedDriver({_HOME: HOME_LOGGED_IN, _MISSION: MISSION_CLAIMABLE})
        status, amount = v2ex.claim_daily(driver)
        self.assertIn("今日已领取", status)
        self.assertEqual("", amount)

    def test_mission_page_says_claimed(self):
        # 任务页自己写着「已成功领取」却没有可领取按钮 —— 今日已领取，不是故障
        driver = ScriptedDriver(
            {_HOME: ERROR_522, _MISSION: MISSION_CLAIMED_CN}, claim_value=None
        )
        status, _ = v2ex.claim_daily(driver)
        self.assertIn("今日已领取", status)

    def test_mission_page_error_raises(self):
        # 站点彻底不可用时必须报错 —— 静默「成功」比失败更可怕
        driver = ScriptedDriver({_HOME: ERROR_522, _MISSION: ERROR_522})
        with self.assertRaises(RuntimeError):
            v2ex.claim_daily(driver)


class ErrorHintTest(unittest.TestCase):
    def test_detects_cloudflare_522(self):
        hint = v2ex.error_hint(FakeDriver(ERROR_522))
        self.assertTrue(hint, "522 错误页必须被认出来")
        print("522 ->", hint)

    def test_detects_nginx_502(self):
        self.assertTrue(v2ex.error_hint(FakeDriver(ERROR_NGINX)))

    def test_detects_cloudflare_block(self):
        self.assertTrue(v2ex.error_hint(FakeDriver(CLOUDFLARE_BLOCK)))

    def test_detects_too_short_page(self):
        self.assertTrue(v2ex.error_hint(FakeDriver("<html>502</html>")))

    def test_normal_home_is_not_error(self):
        self.assertEqual("", v2ex.error_hint(FakeDriver(HOME_LOGGED_IN)))

    def test_signin_page_is_not_error_even_if_short(self):
        # V2EX 登录页源码不算长，但它带 /signin 与 captcha 标记
        self.assertEqual("", v2ex.error_hint(FakeDriver(SIGNIN_PAGE)))

    def test_broken_driver_reports_error(self):
        class Boom(object):
            @property
            def page_source(self):
                raise FakeException("chrome not reachable")

        self.assertTrue(v2ex.error_hint(Boom()))


class IsLoggedInTest(unittest.TestCase):
    def test_error_page_is_not_logged_in(self):
        # 这是本次事故的放大器：错误页既没 /signout 也没验证码框，
        # 旧逻辑会顺着「不在 /signin 页且验证码框消失」把它判成已登录。
        driver = FakeDriver(ERROR_522, url="https://v2ex.com/")
        self.assertFalse(v2ex.is_logged_in(driver))

    def test_home_with_signout_is_logged_in(self):
        driver = FakeDriver(HOME_LOGGED_IN, url="https://v2ex.com/")
        self.assertTrue(v2ex.is_logged_in(driver))

    def test_signin_page_is_not_logged_in(self):
        driver = FakeDriver(SIGNIN_PAGE, url="https://v2ex.com/signin")
        self.assertFalse(v2ex.is_logged_in(driver))


class ClaimedTextTest(unittest.TestCase):
    def test_chinese(self):
        self.assertTrue(v2ex.has_claimed_text(FakeDriver(MISSION_CLAIMED_CN)))

    def test_english(self):
        # CI 是海外 IP，拿到的是英文界面 —— 只认中文会把已领取误判成页面改版
        self.assertTrue(v2ex.has_claimed_text(FakeDriver(MISSION_CLAIMED_EN)))

    def test_claimable_page_is_not_claimed(self):
        self.assertFalse(v2ex.has_claimed_text(FakeDriver(MISSION_CLAIMABLE)))


class ClaimValueTest(unittest.TestCase):
    def test_languages(self):
        for value in ("领取 4 铜币", "Claim 4 coins"):
            self.assertTrue(v2ex.is_claim_value(value))
        # 领取成功后 V2EX 只把文案改成「查看我的账户余额」，按钮还在
        self.assertFalse(v2ex.is_claim_value("查看我的账户余额"))
        self.assertFalse(v2ex.is_claim_value("Check my account balance"))

    def test_amount(self):
        self.assertEqual("4", v2ex.claim_amount("领取 4 铜币"))
        self.assertEqual("12", v2ex.claim_amount("Claim 12 coins"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
