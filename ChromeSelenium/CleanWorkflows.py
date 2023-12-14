# -*- coding: UTF-8 -*-

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC

import os, sys, time, requests, platform, traceback

chrome_options = webdriver.ChromeOptions()

chrome_options.add_argument("--no-sandbox")  # 解决DevToolsActivePort文件不存在的报错
chrome_options.add_argument("--disable-gpu")  # 谷歌文档提到需要加上这个属性来规避bug
# chrome_options.add_argument('--headless')       # 浏览器不提供可视化页面. linux下如果系统不支持可视化不加这条会启动失败

chrome_options.add_argument("window-size=1920x1080")  # 指定浏览器分辨率
chrome_options.add_argument("--disable-dev-shm-usage")

chromedriver = "/usr/bin/chromedriver"
os.environ["webdriver.chrome.driver"] = chromedriver
browser = webdriver.Chrome(chrome_options=chrome_options, executable_path=chromedriver)
browser.implicitly_wait(10)  # 所有的操作都可以最长等待10s

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

# 登录地址
website = "https://github.com/login?return_to=https%3A%2F%2Fgithub.com%2FEchoHeim%2FGithubAction"

browser.get(website)
time.sleep(6)
print(browser.title)

browser.find_element(By.XPATH, '//*[@id="login_field"]').send_keys(username)  # 输入账号
browser.find_element(By.XPATH, '//*[@id="password"]').send_keys(password)  # 输入密码
browser.find_element(By.XPATH, '//*[@value="Sign in"]').click()  # 点击登录
time.sleep(10)
print(browser.title)

num = 0

browser.find_element(By.XPATH, '//*[@id="actions-tab"]').click()  # Actions-tab
time.sleep(8)

browser.find_element(By.XPATH, '//*[@class="next_page"]').click()
print("\n==== 下一页 ====\n")
time.sleep(4)

while True:
    try:
        browser.find_element(By.XPATH, '//*[@aria-label="Show options"]').click()
        time.sleep(2)
        browser.find_element(
            By.XPATH, '//*[@class="dropdown-item btn-link menu-item-danger"]'
        ).click()
        time.sleep(4)
        browser.find_element(By.XPATH, '//*[@class="btn-danger btn btn-block"]').click()
        time.sleep(4)
        num = num + 1
    except:
        print("==== 共清理 %d 条记录 ====\n" % num)
        break

print("\n---- end ----\n")
browser.quit()
