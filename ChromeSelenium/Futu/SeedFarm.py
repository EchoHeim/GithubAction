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

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)


browser.find_element(
    By.XPATH, "/html/body/div[1]/div[2]/div/div[2]/p[3]/a"
).click()  # 登录

browser.find_element(
    By.XPATH, "/html/body/div[1]/div[2]/div/div[2]/form[1]/div[2]/input"
).send_keys(
    username
)  # 输入账号

browser.find_element(
    By.XPATH, "/html/body/div[1]/div[2]/div/div[2]/form[1]/input"
).click()  # 下一步

browser.find_element(By.XPATH, '//*[@id="app"]/div/form/div[2]/input').send_keys(
    password
)  # 输入密码

browser.find_element(By.XPATH, '//*[@id="app"]/div/form/input').click()  # 下一步
print(browser.title)

try:
    num = browser.find_element(By.XPATH, '//*[@class="opBtn waterBtn ng-scope"]').text
    if int(num) == 0:
        print("\n==== 种子已经喝饱了，不需要再浇水！ ====\n")
    else:
        num = int(num) - 1
        print("\n==== 给自己浇水, 剩余 %d 次 ====\n" % int(num))
        browser.find_element(By.XPATH, '//*[@class="waterCanvas"]').click()
except Exception:
    msg = "<font color='red'> 🎋 种子已成熟，需要重新播种！ </font>"
    Feishu_SendCardMsg(bot_id, title, msg)
    print("\n==== 🎋 种子已成熟，需要重新播种！ ====\n")

time.sleep(4)

print("==== 进入好友列表 ====\n")
browser.find_element(By.XPATH, "/html/body/div[1]/div/div[8]/ul/li[3]/a").click()
time.sleep(4)
print("==== 筛选 (可施肥) ====\n")
browser.find_element(By.XPATH, '//*[@class="filter-op"]/span').click()
time.sleep(2)

for i in range(40):
    try:
        browser.find_element(
            By.XPATH, '//*[@class="can_fert icon_friends-fert"]'
        ).click()  # 选中一位好友
        time.sleep(4)
        browser.find_element(By.XPATH, '//*[@class="opIcon icon_fert"]').click()  # 浇水
        time.sleep(4)
        browser.find_element(By.XPATH, '//*[@class="back-home"]/span').click()  # 返回好友列表
        time.sleep(4)
    except Exception:
        msg = (
            f"<font color='blue'> ==== 施肥成功 </font>{str(i)}"
            + "<font color='blue'> 好友 ====</font>\n"
        )
        # Feishu_SendCardMsg(bot_id, title, msg)
        print("==== 施肥成功 %d 好友 ====" % i)
        break

print("\n---- end ----\n")
browser.quit()
