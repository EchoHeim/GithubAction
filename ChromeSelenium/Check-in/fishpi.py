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
driver.get(website)
time.sleep(4)
print(driver.title)

try:
    driver.find_element(By.XPATH, '//*[@autofocus="autofocus"]').send_keys(username)
    driver.find_element(By.XPATH, '//*[@type="password"]').send_keys(password)
    driver.find_element(By.XPATH, "/html/body/div[3]/div/div[1]/div/button[1]").click()
    time.sleep(4)

    print("---> 领取昨日奖励")
    driver.find_element(By.XPATH, '//*[@id="yesterdayImg"]').click()
    time.sleep(2)
except Exception:
    print("fishpi - 领取昨日奖励失败")

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
