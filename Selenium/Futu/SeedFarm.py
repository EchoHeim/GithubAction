#! /usr/bin/env python3
# -*- coding: UTF-8 -*-

# sourcery skip: avoid-builtin-shadow
import json
import sys

from Selenium.base import *
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


# ---------- 种子成熟检测 ----------
# 生长期气泡文案为「生命剩下X天Y小时」（见截图），成熟后气泡会换成收获类文案、
# 并出现「收获」按钮。页面由 Angular 渲染，类名可能随版本变动，因此同时用三类信号
# 判定：收获类元素可见 / 成熟关键词文案 / 生命时长归零。命中任一即视为成熟。
HARVEST_SELECTORS = [
    "[class*='harvest']",
    "[class*='Harvest']",
    "[class*='mature']",
    "[class*='Mature']",
    "[class*='shouhuo']",
    ".opBtn.harvestBtn",
]
MATURE_KEYWORDS = ["已成熟", "成熟了", "可收获", "立即收获", "去收获", "采摘", "可以收获"]

# 一次 JS 扫描拿全：成熟信号 + 生命时长气泡 + 今日剩余浇水次数
FARM_PROBE_JS = r"""
var out = {mature: false, evidence: [], hints: [], life: '', waterCount: null};
var body = document.body;
if (!body) { return out; }
var text = body.innerText || '';

// 1) 生命时长气泡：生长期形如「生命剩下4天09小时」，归零即成熟
var m = text.match(/生命剩下\s*(\d+)\s*天\s*(\d+)\s*小时/);
if (m) {
    out.life = m[0].replace(/\s+/g, '');
    if (parseInt(m[1], 10) === 0 && parseInt(m[2], 10) === 0) {
        out.mature = true;
        out.evidence.push('life-zero:' + out.life);
    }
}

// 2) 收获类控件可见 => 成熟
var sels = %(sels)s;
for (var i = 0; i < sels.length && !out.mature; i++) {
    var els = document.querySelectorAll(sels[i]);
    for (var j = 0; j < els.length; j++) {
        var el = els[j];
        if (el.offsetParent === null) { continue; }
        out.mature = true;
        out.evidence.push('selector:' + sels[i] + '|' + (el.innerText || '').trim().slice(0, 20));
        break;
    }
}

// 3) 文案兜底
if (!out.mature) {
    var kws = %(kws)s;
    for (var k = 0; k < kws.length; k++) {
        if (text.indexOf(kws[k]) !== -1) {
            out.mature = true;
            out.evidence.push('keyword:' + kws[k]);
            break;
        }
    }
}

// 4) 采集相关文案，便于失败时反推选择器
var nodes = document.querySelectorAll('body *');
var seen = 0;
for (var p = 0; p < nodes.length && seen < 6; p++) {
    var n = nodes[p];
    if (n.children.length > 0) { continue; }
    var t = (n.innerText || '').trim();
    if (!t || t.length > 24) { continue; }
    if (/生命剩下|成熟|收获|采摘|浇水/.test(t)) {
        out.hints.push((n.className || n.tagName) + '|' + t);
        seen++;
    }
}

// 5) 今日剩余浇水次数
var badges = document.querySelectorAll('.opBtn.waterBtn .water_num');
for (var b = 0; b < badges.length; b++) {
    var raw = (badges[b].textContent || '').trim();
    if (/^\d+$/.test(raw)) { out.waterCount = parseInt(raw, 10); break; }
}
return out;
""" % {
    "sels": json.dumps(HARVEST_SELECTORS),
    "kws": json.dumps(MATURE_KEYWORDS, ensure_ascii=False),
}


def probe_farm(browser):
    """扫描农场当前状态；脚本注入失败时返回保守默认值，不中断主流程。"""
    try:
        return browser.execute_script(FARM_PROBE_JS) or {}
    except Exception as e:
        print("[WARN] 农场状态扫描失败:", e)
        return {
            "mature": False,
            "evidence": [],
            "hints": [],
            "life": "",
            "waterCount": None,
        }


def inspect_seed(browser, timeout=30):
    """等待农场数据就绪（浇水次数插值完成）或种子成熟，返回最终状态。"""
    deadline = time.time() + timeout
    state = probe_farm(browser)
    while time.time() < deadline:
        if state.get("mature") or state.get("waterCount") is not None:
            return state
        time.sleep(1)
        state = probe_farm(browser)
    state["timeout"] = True
    return state


def find_water_button(driver):
    """取带数字徽标的那颗浇水按钮，保持与旧逻辑一致的匹配口径。"""
    for button in driver.find_elements(By.CSS_SELECTOR, ".opBtn.waterBtn"):
        try:
            badge = button.find_element(By.CSS_SELECTOR, ".water_num")
            raw_count = (badge.get_attribute("textContent") or "").strip()
            if raw_count.isdigit():
                return button
        except Exception:
            continue
    return None


def notify_seed_matured(browser, state):
    """种子成熟 -> 单独推送一条飞书提醒；推送/截图失败都不阻断后续好友操作。"""
    life = state.get("life") or "未知"
    evidence = " / ".join(state.get("evidence") or [])[:180] or "收获控件出现"
    print("\n==== [成熟] 种子已成熟 ==== life=%s evidence=%s\n" % (life, evidence))
    print("[LOG] 页面线索: %s" % (state.get("hints") or []))

    try:
        dump_debug(browser, "mature")
    except Exception as e:  # noqa
        print("[WARN] 成熟截图失败:", e)

    msg = (
        "<font color='red'> 🌾 种子已成熟，记得上线收获！ </font>\n"
        "<font color='grey'> ⏳ 生命时长：%s </font>\n" % life
        + "<font color='grey'> 🔎 判定依据：%s </font>" % evidence
    )
    try:
        Feishu_SendCardMsg(bot_id, title + "｜成熟提醒", msg)
    except Exception as e:  # 网络抖动不能拖垮浇水主流程
        print("[WARN] 成熟提醒发送失败（继续给好友浇水）:", e)


OVERLAY_SELECTORS = [
    "[class*='mask']",
    "[class*='Mask']",
    "[class*='modal']",
    "[class*='dialog']",
    "[class*='popup']",
    "[class*='pop-layer']",
]
OVERLAY_CLOSE_TEXTS = ["我知道了", "知道啦", "知道了", "确定", "关闭", "稍后再说"]


def dismiss_overlay(browser):
    """成熟后页面常弹「可收获」浮层，会挡住「互动 / 施肥」的点击。
    只做温和处理：先按 ESC，再点浮层内的关闭类控件；失败一律不抛错。"""
    try:
        # 只认「内容与成熟/关闭相关」的浮层：页面上长期存在的背景 mask 不能被误点。
        mask = None
        for sel in OVERLAY_SELECTORS:
            for el in browser.find_elements(By.CSS_SELECTOR, sel):
                try:
                    if not el.is_displayed():
                        continue
                    label = (el.text or "").strip()
                except Exception:
                    continue
                if any(k in label for k in MATURE_KEYWORDS) or any(
                    t in label for t in OVERLAY_CLOSE_TEXTS
                ):
                    mask = el
                    break
            if mask is not None:
                break
        if mask is None:
            return False

        print("[LOG] 检测到浮层，尝试关闭")
        try:
            ActionChains(browser).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
        except Exception:
            pass
        for text in OVERLAY_CLOSE_TEXTS:
            # 只点标签级控件；不用 div，避免命中包裹整个弹层的大容器
            for tag in ("a", "button", "span"):
                try:
                    el = mask.find_element(
                        By.XPATH,
                        ".//%s[contains(normalize-space(.),'%s')]" % (tag, text),
                    )
                    if el.is_displayed():
                        el.click()
                        print("[LOG] 已关闭浮层: %s" % text)
                        time.sleep(1)
                        return True
                except Exception:
                    continue
        return False
    except Exception as e:  # 关不掉也要继续走好友流程
        print("[WARN] 关闭浮层失败（忽略）:", e)
        return False


def farm(browser):
    # 外层 opBtnBox 初始为 display:none，由 Angular 指令在数据就绪后处理。
    # Selenium 的可见性判断在 headless 环境里不可靠，因此直接扫描页面状态：
    # 既能读到今日剩余浇水次数，也能识别「种子已成熟」——成熟时页面通常没有浇水入口，
    # 旧逻辑会在这里超时抛错，把后面的好友互动整段跳过，所以必须先判定再决定是否浇水。
    state = inspect_seed(browser)
    matured = bool(state.get("mature"))
    if matured:
        notify_seed_matured(browser, state)

    before_count = state.get("waterCount")
    water_button = None
    if not matured:
        if before_count is None:
            raise AssertionError(
                "农场数据加载超时：未检测到成熟信号，也读不到今日剩余浇水次数 %s"
                % (state.get("hints") or [])
            )
        water_button = find_water_button(browser)

    watered = False
    if matured:
        print("\n==== 种子已成熟，跳过自家浇水，直接去好友列表 ====\n")
    elif before_count > 0:
        if water_button is None:
            water_button = find_water_button(browser)
        if water_button is None:
            raise AssertionError("今日仍有 %d 次浇水机会，但找不到浇水按钮" % before_count)
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

    if matured:
        dismiss_overlay(browser)

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

    if matured:
        water_summary = "🌾 种子已成熟，本次未浇水（已单独发飞书提醒）"
    elif watered:
        water_summary = "💧 已给当前种子浇水"
    else:
        water_summary = "💧 今日浇水次数已用完"
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
