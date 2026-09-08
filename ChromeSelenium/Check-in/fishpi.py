# -*- coding: UTF-8 -*-

import sys
import os

current_folder = os.path.dirname(os.path.abspath(__file__))
print("当前脚本所在文件夹路径:", current_folder)

sys.path.append("current_folder/../")  # 添加自定义模块路径
from ChromeSelenium.base import *
from Messaging.Msg import *


from ChromeSelenium.base import *
from Messaging.Msg import *

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

website = "https://fishpi.cn/login?goto=https%3A%2F%2Ffishpi.cn%2F"

driver = get_web_driver()
open_page(driver, website)
time.sleep(4)
print(driver.title)

try:
    WebDriverWait(driver, 20).until(
        EC.visibility_of_element_located((By.ID, "nameOrEmail"))
    ).send_keys(username)
    driver.find_element(By.ID, "loginPassword").send_keys(password)
    WebDriverWait(driver, 30).until(
        lambda current: current.execute_script(
            "return typeof window.Verify === 'object' "
            "&& typeof window.Verify.login === 'function';"
        )
    )
    WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable(
            (By.XPATH, "//button[contains(@onclick, 'Verify.login')]")
        )
    ).click()

    # 登录成功后首页至少会出现奖励入口或聊天室；停留在登录/访客验证页不算成功。
    WebDriverWait(driver, 20).until(
        lambda current: current.find_elements(By.ID, "yesterdayImg")
        or current.find_elements(By.ID, "chatRoomInput")
    )
    print("fishpi - 登录成功")

    print("---> 领取昨日奖励")
    driver.find_element(By.XPATH, '//*[@id="yesterdayImg"]').click()
    time.sleep(2)
except Exception as exc:
    print(
        "fishpi - 登录或领取昨日奖励失败: %s (title=%s url=%s)"
        % (exc, driver.title, driver.current_url)
    )
    print("===== FISHPI LOGIN STRUCTURE =====")
    for index, element in enumerate(driver.find_elements(By.CSS_SELECTOR, "input")):
        print(
            "input#%d id=%r type=%r placeholder=%r visible=%s"
            % (
                index,
                element.get_attribute("id"),
                element.get_attribute("type"),
                element.get_attribute("placeholder"),
                element.is_displayed(),
            )
        )
    for index, element in enumerate(driver.find_elements(By.CSS_SELECTOR, "button")):
        print(
            "button#%d text=%r onclick=%r visible=%s"
            % (
                index,
                element.text,
                element.get_attribute("onclick"),
                element.is_displayed(),
            )
        )
    for index, frame in enumerate(driver.find_elements(By.CSS_SELECTOR, "iframe")):
        print(
            "iframe#%d title=%r src=%r visible=%s"
            % (
                index,
                frame.get_attribute("title"),
                frame.get_attribute("src"),
                frame.is_displayed(),
            )
        )
    for selector in (
        "#loginTip",
        "#captcha",
        "[class*='captcha']",
        "[class*='geetest']",
        "[class*='verify']",
    ):
        for index, element in enumerate(driver.find_elements(By.CSS_SELECTOR, selector)):
            print(
                "state selector=%r index=%d text=%r class=%r visible=%s"
                % (
                    selector,
                    index,
                    element.text,
                    element.get_attribute("class"),
                    element.is_displayed(),
                )
            )
    print("===== END FISHPI LOGIN STRUCTURE =====")

try:
    print("---> 聊天发言 1")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 2")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("开始摸鱼~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 3")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 4")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("di~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 5")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("Are you OK?")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 6")
    driver.find_element(By.XPATH, '//*[@id="chatRoomInput"]').send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)
except Exception:
    print("fishpi - 聊天发言失败")

try:
    print("---> 浏览第一篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[8]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[4]/div/span[2]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第二篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[10]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[4]/div/span[2]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第三篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[12]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[4]/div/span[2]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第三篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[13]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[4]/div/span[2]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第三篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[14]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[4]/div/span[2]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第三篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[9]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)

    print("---> 浏览第三篇文章")
    driver.find_element(
        By.XPATH, "/html/body/div[4]/div[2]/div[1]/div[2]/ul/li[11]"
    ).click()
    time.sleep(6)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(4)
    driver.back()

except Exception:
    print("fishpi - 签到失败")

driver.quit()
