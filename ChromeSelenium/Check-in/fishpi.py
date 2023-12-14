# -*- coding: UTF-8 -*-

import sys

from ChromeSelenium.base import *
from Messaging.Msg import *

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

website = "https://fishpi.cn/login?goto=https%3A%2F%2Ffishpi.cn%2F"

driver = get_web_driver()
driver.get(website)
time.sleep(4)
print(browser.title)

try:
    driver.find_element(By.XPATH, '//*[@autofocus="autofocus"]').send_keys(username)
    driver.find_element(By.XPATH, '//*[@type="password"]').send_keys(password)
    driver.find_element(By.XPATH, "/html/body/div[3]/div/div[1]/div/button[1]").click()
    time.sleep(4)

    print("---> 领取昨日奖励")
    driver.find_element(By.XPATH, '//*[@id="yesterdayImg"]').click()
    time.sleep(2)
except:
    print("fishpi - 领取昨日奖励失败")

try:
    print("---> 聊天发言 1")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 2")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("凌 信息")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 3")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 4")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("di~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 5")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("Are you OK?")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)

    print("---> 聊天发言 6")
    driver.find_element(
        By.XPATH, '//*[@placeholder="简单聊聊 (高级功能请访问完整版聊天室哦)"]'
    ).send_keys("hello~")
    driver.find_element(By.XPATH, "//*[@onclick='sendChat()']").click()
    time.sleep(300)
except:
    print("fishpi - 聊天发言失败")

try:
    print("---> 浏览文章")
    driver.find_element(By.XPATH, '//*[@id="randomArticles"]/li[4]/a[2]').click()
    time.sleep(4)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(2)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[12]/div/span[1]").click()

    driver.back()
    print("---> 返回上一页")
    time.sleep(6)
    print("---> 浏览文章")
    driver.find_element(By.XPATH, '//*[@id="randomArticles"]/li[6]/a[2]').click()
    time.sleep(4)
    driver.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    time.sleep(2)
    print("---> 文章点赞")
    driver.find_element(By.XPATH, "/html/body/div[12]/div/span[1]").click()
except:
    print("fishpi - 签到失败")

driver.quit()
