# -*- coding: UTF-8 -*-

# sourcery skip: avoid-builtin-shadow

import sys
import os

current_folder = os.path.dirname(os.path.abspath(__file__))
print("当前脚本所在文件夹路径:", current_folder)
sys.path.append("current_folder/../")  # 添加自定义模块路径

from ChromeSelenium.base import *
from Messaging.Msg import *
from bs4 import BeautifulSoup


username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

bot_id = sys.argv[3]  # 机器人编号

website = "https://www.coarcade.com/"

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)

title = "好玩游戏厅"
msg = ""

try:
    browser.find_element(
        By.XPATH, "/html/body/div/header/div/div/div[4]/div[1]"
    ).click()  # 点击登录

    browser.find_element(By.XPATH, '//*[@id="login"]/div/form/div[1]/input').send_keys(
        username
    )
    browser.find_element(By.XPATH, '//*[@id="login"]/div/form/div[2]/input').send_keys(
        password
    )

    browser.find_element(By.XPATH, '//*[@id="login"]/div/form/button').click()  # 安全登录按钮

    time.sleep(4)
    print("\n===> Coarcade 登录成功!")

except Exception:
    print("\n===> Coarcade 登录失败!")
    msg += "<font color='red'> ---- 登录失败! ---- </font>\n"


try:
    time.sleep(4)
    browser.find_element(
        By.XPATH, "/html/body/div/header/div/div/div[4]/div[1]/div[1]/a"
    ).click()  # 个人信息页

    time.sleep(10)

    html_content = browser.page_source  # 抓取当前网页数据

    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(html_content, "html.parser")

    # 查找特定类名的元素
    if element := soup.find("div", class_="author-info mcolorbg4"):
        num = element.find("h3").text
        print("签到前，积分:", num)
    else:
        print("未找到特定元素")

    msg += f"<font color='green'> 🎋 昨日积分： </font>{str(num)}" + " \n"

except Exception:
    msg += "<font color='orange'> 🎋 积分获取失败！ </font>\n"


try:
    browser.find_element(
        By.XPATH, "/html/body/div/header/div/div/div[1]/a/img"
    ).click()  # 返回首页
    time.sleep(10)
    browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    browser.find_element(By.XPATH, "/html/body/div/div[3]/div[2]").click()  # 签到

    time.sleep(2)
    browser.refresh()  # 刷新网页
    time.sleep(5)
    browser.execute_script("window.scrollBy(0,-400)")  # 向上滑动400个像素
    print("\n===> Coarcade 签到成功!")
    msg += "<font color='blue'> ---- 签到成功! ---- </font>\n"

except Exception:
    print("\n===> Coarcade 签到失败!")
    msg += "<font color='red'> ---- 签到失败! ---- </font>\n"

try:
    time.sleep(4)
    browser.find_element(
        By.XPATH, "/html/body/div/header/div/div/div[4]/div[1]/div[1]/a"
    ).click()  # 个人信息页

    time.sleep(10)

    html_content = browser.page_source  # 抓取当前网页数据

    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(html_content, "html.parser")

    # 查找特定类名的元素
    if element := soup.find("div", class_="author-info mcolorbg4"):
        num = element.find("h3").text
        print("积分:", num)
    else:
        print("未找到特定元素")

    msg += f"<font color='green'> 🎋 当前积分： </font>{str(num)}" + " \n"

except Exception:
    msg += "<font color='orange'> 🎋 积分获取失败！ </font>\n"

Feishu_SendCardMsg(bot_id, title, msg)

# 退出Chrome
browser.quit()
