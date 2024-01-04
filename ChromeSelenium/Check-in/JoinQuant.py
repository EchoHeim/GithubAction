# -*- coding: UTF-8 -*-

import sys
import os

current_folder = os.path.dirname(os.path.abspath(__file__))
print("当前脚本所在文件夹路径:", current_folder)

sys.path.append("current_folder/../")  # 添加自定义模块路径
from ChromeSelenium.base import *
from Messaging.Msg import *


username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

bot_id = sys.argv[3]  # 机器人编号

website = "https://www.joinquant.com/user/login/index?type=login"

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)

title = " JoinQuant "
msg = ""

try:
    browser.find_element(By.XPATH, '//*[@class="phone pwd-phone"]').send_keys(username)
    browser.find_element(By.XPATH, '//*[@class="jq-login__password"]').send_keys(
        password
    )
    browser.find_element(
        By.XPATH, '//*[@class="login-submit btnPwdSubmit"]'
    ).click()  # 点击登录
    time.sleep(4)
    print(browser.title)

except Exception:
    print("\n===> JoinQuant 登录失败!")
    msg += " ---- 登录失败! ---- \n"

# 显示当前积分
try:
    time.sleep(10)
    # 点击 积分 页
    browser.find_element(
        By.XPATH, "/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]"
    ).click()

    time.sleep(10)
    num = browser.find_element(
        By.XPATH, "/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]/span[2]"
    ).text
    print("\n---> JoinQuant: 当前积分 %d \n" % int(num))
    msg += "签到前 \n <font color='green'> 昨日积分: </font>" + str(num) + "\n"
except Exception:
    print("\n===> Err: < 显示当前积分 >")
    msg += "---- 无法显示积分! ----\n"

try:
    # 点击 积分 页
    browser.find_element(
        By.XPATH, "/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]"
    ).click()
    time.sleep(4)
    # 签到
    browser.find_element(
        By.XPATH,
        "/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[2]/div[2]/div[2]/div/button",
    ).click()
    time.sleep(2)
except Exception:
    print("\n===> JoinQuant 签到失败!")
    msg += "---- 签到失败! ----\n"

try:
    # 进入社区页面
    browser.find_element(
        By.XPATH,
        "/html/body/section/div/ul/li[4]/a",
    ).click()
    time.sleep(4)
    print(browser.title)
except Exception:
    print("\n===> Err: < 进入社区页面 >")
    msg += "---- 无法进入社区页面! ----\n"

try:
    # 浏览文章
    browser.find_element(
        By.XPATH,
        "/html/body/section/main/div/div[2]/div[1]/div[3]/div[1]/div[4]/div/div[1]/div[1]",
    ).click()
    browser.switch_to.window(browser.window_handles[1])  # 切换页面
    time.sleep(4)
    browser.refresh()  # 刷新页面
    time.sleep(4)
    browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    print(browser.title)
except Exception:
    print("\n===> Err: < 浏览文章 >")
    msg += "\n > ---- 无法浏览文章! ----"

try:
    browser.switch_to.window(browser.window_handles[0])  # 切换回第一个页面

    browser.find_element(
        By.XPATH, "/html/body/section/div/ul/li[1]/a/span"
    ).click()  # 回到首页

    time.sleep(5)

    # 点击 积分 页
    browser.find_element(
        By.XPATH, "/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]"
    ).click()
    time.sleep(2)
    print("\n==== 返回积分主页 ====")
    browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素

except Exception:
    print("\n===> Err: < 积分首页 >")
    msg += "---- 返回首页失败! ----\n"

# 领取积分
try:
    browser.find_element(
        By.XPATH,
        "/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/button",
    ).click()
    time.sleep(4)
except Exception:
    print("\n===> JoinQuant 积分领取失败!")
    msg += "---- 积分领取失败! ----\n"

# 显示当前积分
try:
    time.sleep(20)
    num = browser.find_element(
        By.XPATH, "/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]/span"
    ).text
    print("\n---> JoinQuant: 当前积分 %d \n" % int(num))
    msg += "签到后 \n <font color='blue'> 当前积分: </font>" + str(num) + "\n"
except Exception:
    print("\n===> Err: < 显示当前积分 >")
    msg += "---- 无法显示积分! ----\n"

Feishu_SendCardMsg(bot_id, title, msg)

# 退出Chrome
browser.quit()
