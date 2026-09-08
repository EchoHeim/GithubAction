#! /usr/bin/env python3
# -*- coding: UTF-8 -*-

# sourcery skip: avoid-builtin-shadow
import sys

from ChromeSelenium.base import *
from Messaging.Msg import *

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码
bot_id = sys.argv[3]  # 机器人编号

title = "富途种子"
msg = ""

# 富途牛牛 种子农场 登录地址
website = "https://passport.futunn.com/?target=https%3A%2F%2Fseed.futunn.com%2F%3Flang%3Dzh-cn%26panel%3Dcultureroom#login"


def dump_debug(browser, tag="overall"):
    """任何一步失败都把当前页面截图 + HTML 导出来，方便下次直接改选择器。"""
    try:
        png = "/tmp/futu_%s.png" % tag
        browser.save_screenshot(png)
        print("[DEBUG] screenshot -> %s" % png)
    except Exception as e:  # noqa
        print("[DEBUG] screenshot failed:", e)
    try:
        html = "/tmp/futu_%s.html" % tag
        with open(html, "w", encoding="utf-8") as f:
            f.write(browser.page_source)
        print("[DEBUG] page_source -> %s" % html)
    except Exception as e:  # noqa
        print("[DEBUG] dom dump failed:", e)
    try:
        print("[DEBUG] title=%s url=%s" % (browser.title, browser.current_url))
    except Exception:
        pass


def dump_login_structure(driver):
    """失败时把登录页结构打成明文日志，方便精确定位。"""
    print("===== LOGIN PAGE STRUCTURE =====")
    try:
        inputs = driver.find_elements(By.TAG_NAME, "input")
        for i, el in enumerate(inputs):
            try:
                placeholder = el.get_attribute("placeholder")
                typ = el.get_attribute("type")
                name = el.get_attribute("name")
                visible = el.is_displayed()
                if placeholder or typ in ("text", "password", "tel", "number", "email"):
                    print(
                        "input#%d type=%s placeholder=%r name=%r visible=%s"
                        % (i, typ, placeholder, name, visible)
                    )
            except Exception:
                pass
    except Exception as e:
        print("inputs err", e)
    try:
        seen = set()
        for tag in ("a", "button"):
            for el in driver.find_elements(By.TAG_NAME, tag):
                try:
                    t = (el.text or "").strip()
                    if t and t not in seen:
                        seen.add(t)
                        print("clickable<%s>: %s" % (tag, t[:40]))
                except Exception:
                    pass
    except Exception as e:
        print("clickables err", e)
    try:
        src = driver.page_source
        for kw in ("滑块", "拼图", "验证码", "captcha", "verify", "滑动"):
            if kw in src:
                print("CAPTCHA-KW:", kw)
    except Exception:
        pass
    print("===== END STRUCTURE =====")


def fill_by_name(driver, names, value, timeout=8):
    """按 name 精确定位输入框（比 placeholder 稳，避免跨 tab 误填）。"""
    for name in names:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@name='%s']" % name))
            )
            el.clear()
            el.send_keys(value)
            print("[LOG] 已填入输入框(name=%s)" % name)
            return el
        except Exception:
            continue
    raise AssertionError("找不到输入框 name: %s" % names)


def click_submit(driver, values=("下一步", "登录"), timeout=8):
    """点击当前可见、未禁用的提交按钮（input[type=submit] / button）。"""
    for v in values:
        for xp in (
            "//input[@type='submit' and contains(@value,'%s') and not(contains(@class,'disabled'))]" % v,
            "//button[contains(normalize-space(.),'%s') and not(contains(@class,'disabled'))]" % v,
        ):
            try:
                el = WebDriverWait(driver, timeout).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                el.click()
                print("[LOG] 已点击提交按钮: %s" % v)
                return el
            except Exception:
                continue
    raise AssertionError("找不到可点击的提交按钮: %s" % (values,))


def find_by_placeholder(driver, subs, value, timeout=8):
    """依次尝试多个 placeholder 关键字，填入目标输入框。"""
    for sub in subs:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//input[contains(@placeholder,'%s')]" % sub)
                )
            )
            el.clear()
            el.send_keys(value)
            print("[LOG] 已填入输入框(placeholder 含: %s)" % sub)
            return el
        except Exception:
            continue
    try:
        ctx = "title=%s url=%s" % (driver.title, driver.current_url)
    except Exception:
        ctx = "unknown"
    raise AssertionError("找不到输入框, 尝试过的 placeholder: %s (%s)" % (subs, ctx))


def click_by_text(driver, texts, tag="*", timeout=8, ignore=False):
    """依次尝试多个可见文本，点击与之匹配的可点元素。"""
    for t in texts:
        for tg in (tag, "a", "button", "input"):
            try:
                xpath = "//%s[contains(normalize-space(.),'%s')]" % (tg, t)
                el = wait_for_visible_enabled(driver, By.XPATH, xpath, timeout)
                el.click()
                print("[LOG] 已点击(文本含: %s, 标签: <%s>)" % (t, tg))
                return el
            except Exception:
                continue
    if ignore:
        print("[LOG] 未找到可点文本: %s（继续）" % texts)
        return None
    raise AssertionError("找不到可点元素, 尝试过的文本: %s" % texts)


def wait_for_visible_enabled(driver, by, locator, timeout=10):
    """等待并返回全部匹配元素中第一个可见、可用的元素。"""

    def find_visible(d):
        for candidate in d.find_elements(by, locator):
            try:
                if candidate.is_displayed() and candidate.is_enabled():
                    return candidate
            except Exception:
                continue
        return False

    return WebDriverWait(driver, timeout).until(find_visible)


def click_switch(driver, texts, timeout=8, ignore=True):
    """点击当前可见的登录方式切换按钮，跳过 DOM 中的隐藏副本。"""
    for t in texts:
        xp = "//a[contains(@class,'switch-btn')][normalize-space(.)='%s']" % t
        try:
            el = wait_for_visible_enabled(driver, By.XPATH, xp, timeout)
            el.click()
            print("[LOG] 已点击切换: %s" % t)
            return el
        except Exception:
            continue
    if ignore:
        print("[LOG] 未找到切换: %s（继续）" % (texts,))
        return None
    raise AssertionError("找不到切换按钮: %s" % (texts,))


def login(browser):
    print(browser.title)

    # 确保在「登录」页签（页面有时默认停在「注册」，需切一下）
    click_switch(browser, ["登录"], ignore=False)

    # 切到「邮箱 / 牛牛号」登录方式（默认是手机+验证码，没有密码框）
    click_switch(browser, ["邮箱/牛牛号"], ignore=False)

    # 账号：按 name=account 精确定位（别被 email 的「邮箱地址」placeholder 抢先匹配）
    try:
        fill_by_name(browser, ["account"], username)
    except Exception:
        find_by_placeholder(browser, ["牛牛号", "账号"], username)

    # 第一步提交
    click_submit(browser, ("下一步",))

    # 第二步：输入密码
    find_by_placeholder(
        browser,
        ["请输入密码", "登录密码", "密码", "password"],
        password,
    )

    # 第二步提交（下一步 / 登录）
    click_submit(browser)

    # 等页面跳转到种子农场
    time.sleep(5)
    print(browser.title)

    if "passport" in (browser.current_url or ""):
        print("[WARN] 仍在登录页，可能触发了滑块/图形验证码")
        dump_debug(browser, "login-after")
        raise AssertionError("登录后仍停留在 passport 页面")
    return browser


def farm(browser):
    # 外层 opBtnBox 初始为 display:none，由 Angular 指令在数据就绪后处理。
    # Selenium 的可见性判断在 headless 环境里不可靠，因此等待次数插值完成，
    # 再触发页面自身 ng-click="water()" 所在的节点。
    def ready_water_control(d):
        for button in d.find_elements(By.CSS_SELECTOR, ".opBtn.waterBtn"):
            try:
                badge = button.find_element(By.CSS_SELECTOR, ".water_num")
                raw_count = (badge.get_attribute("textContent") or "").strip()
                if raw_count.isdigit():
                    return button, int(raw_count)
            except Exception:
                continue
        return False

    try:
        water_button, before_count = WebDriverWait(browser, 30).until(
            ready_water_control
        )
    except Exception as e:
        raise AssertionError("农场数据加载超时，无法读取今日剩余浇水次数") from e

    watered = False
    if before_count > 0:
        browser.execute_script("arguments[0].click();", water_button)

        def water_count_decreased(d):
            for badge in d.find_elements(
                By.CSS_SELECTOR, ".opBtn.waterBtn .water_num"
            ):
                raw_count = (badge.get_attribute("textContent") or "").strip()
                if raw_count.isdigit() and int(raw_count) < before_count:
                    return (int(raw_count),)
            return False

        try:
            after_count = WebDriverWait(browser, 15).until(water_count_decreased)[0]
        except Exception as e:
            raise AssertionError("已触发浇水，但剩余次数没有减少") from e

        watered = True
        print("\n==== 已给当前种子浇水，今日剩余 %d 次 ====\n" % after_count)
    else:
        print("\n==== 今日浇水次数已用完，继续检查可施肥好友 ====\n")

    time.sleep(4)

    print("==== 进入好友列表 ====\n")
    try:
        click_by_text(browser, ["互动"], tag="a", timeout=5)
    except Exception:
        browser.find_element(
            By.XPATH, "/html/body/div[1]/div/div[8]/ul/li[3]/a"
        ).click()
    time.sleep(4)

    print("==== 筛选 (可施肥) ====\n")
    try:
        click_by_text(browser, ["可施肥"], tag="span", timeout=5)
    except Exception:
        browser.find_element(By.CSS_SELECTOR, ".filter-op > span").click()
    time.sleep(2)

    fertilized = 0
    for _ in range(40):
        candidates = [
            candidate
            for candidate in browser.find_elements(
                By.CSS_SELECTOR, ".can_fert.icon_friends-fert"
            )
            if candidate.is_displayed() and candidate.is_enabled()
        ]
        if not candidates:
            break

        try:
            candidates[0].click()
            time.sleep(4)

            wait_for_visible_enabled(
                browser, By.CSS_SELECTOR, ".opIcon.icon_fert"
            ).click()
            time.sleep(4)

            wait_for_visible_enabled(
                browser, By.CSS_SELECTOR, ".back-home > span"
            ).click()
            fertilized += 1
            time.sleep(4)
        except Exception as e:
            raise AssertionError(
                "给第 %d 位好友施肥时失败" % (fertilized + 1)
            ) from e

    water_summary = "💧 已给当前种子浇水" if watered else "💧 今日浇水次数已用完"
    msg = (
        "<font color='green'> %s </font>\n" % water_summary
        + "<font color='blue'> 🌱 已给 %d 位好友施肥 </font>" % fertilized
    )
    Feishu_SendCardMsg(bot_id, title, msg)
    print("==== 施肥成功 %d 位好友 ====" % fertilized)


def main():
    browser = get_web_driver()
    try:
        browser.get(website)
        time.sleep(4)
        login(browser)
        farm(browser)
    except Exception as e:
        print("[ERROR]", e)
        action_error = (
            str(e).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        )
        print("::error title=Futu automation failed::%s" % action_error)
        try:
            dump_login_structure(browser)
        except Exception:
            pass
        try:
            dump_debug(browser, "error")
        except Exception:
            pass
        raise
    finally:
        print("\n---- end ----\n")
        browser.quit()


if __name__ == "__main__":
    main()
