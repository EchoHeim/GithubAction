# -*- coding: UTF-8 -*-

# sourcery skip: avoid-builtin-shadow
import os, sys

current_folder = os.path.dirname(os.path.abspath(__file__))
print("当前脚本所在文件夹路径:", current_folder)

sys.path.append("current_folder/../")  # 添加自定义模块路径

from ChromeSelenium.base import *
from Messaging.Msg import *

from bs4 import BeautifulSoup

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

website = "https://www.aliyundrive.com/drive/file/backup"

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)

str = " ## 阿里云盘"

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
    print("\n===> 阿里云盘 登录成功!")

except Exception:
    print("\n===> 阿里云盘 登录失败!")
    str += "\n > ---- 登录失败! ----"

try:
    time.sleep(4)
    browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素

    browser.find_element(By.XPATH, "/html/body/div/div[3]/div[2]").click()  # 签到

    time.sleep(1)
    browser.refresh()  # 刷新网页
    time.sleep(5)


except Exception:
    print("\n===> 阿里云盘 签到失败!")
    str += "\n > ---- 签到失败! ----"

try:
    time.sleep(4)
    browser.find_element(
        By.XPATH, "/html/body/div/header/div/div/div[4]/div[1]/div[1]/a/span"
    ).click()  # 个人信息页

    time.sleep(4)

    html_content = browser.page_source  # 抓取当前网页数据

    # 使用Beautiful Soup解析HTML内容
    soup = BeautifulSoup(html_content, "html.parser")

    # 查找特定类名的元素
    if element := soup.find("div", class_="author-info mcolorbg4"):
        num = element.find("h3").text
        print("积分:", num)
    else:
        print("未找到特定元素")

    str = str + "  \n <font color=#22a2c3> 🎋 当前积分： </font>" + num + " "
    DingTalk_SendMsg("GitAction", str)

except Exception:
    str += "\n <font color=#22a2c3> 🎋 积分获取失败！ </font>"
    DingTalk_SendMsg("GitAction", str)

# 退出Chrome
browser.quit()
