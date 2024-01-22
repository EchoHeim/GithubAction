# -*- coding: UTF-8 -*-

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC

import os, sys, time, requests, platform, traceback
from selenium.webdriver.chrome.service import Service


service = Service()
options = webdriver.ChromeOptions()
if platform.system() == "Windows":
    print("\nCurrent Operating System: ==== Windows ====\n")
    browser = webdriver.Chrome(service=service, options=options)
elif platform.system() == "Linux":
    print("\nCurrent Operating System: ==== Linux ====\n")
    chromedriver = "/usr/bin/chromedriver"
    os.environ["webdriver.chrome.driver"] = chromedriver
    if "fv-az" in platform.node():  # github actions 服务器名
        chrome_options.add_argument(
            "--headless"
        )  # 浏览器不提供可视化页面. linux下如果系统不支持可视化不加这条会启动失败
    browser = webdriver.Chrome(
        chrome_options=chrome_options, executable_path=chromedriver
    )

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

time.sleep(50)  # 延时等待，需要手动进行二次验证

browser.get(website)
time.sleep(6)
print(browser.title)

num = 0

browser.find_element(By.XPATH, '//*[@id="actions-tab"]').click()  # Actions-tab
time.sleep(8)

browser.find_element(By.XPATH, '//*[@class="next_page"]').click()
print("\n==== 第二页 ====\n")
time.sleep(4)

while True:
    try:
        browser.find_element(
            By.XPATH,
            "/html/body/div[1]/div[6]/div/main/turbo-frame/div/split-page-layout/div/div/div[2]/div/div/div[2]/div[2]/div[1]/div/div[3]/div/div[2]",
        ).click()
        print("==== 点击展开选项 ====\n")
        time.sleep(2)

        browser.find_element(By.XPATH, '//*[@class="text-left"]').click()
        print("==== 删除 ====\n")
        time.sleep(4)

        browser.find_element(
            By.XPATH,
            "/html/body/div[1]/div[6]/div/main/turbo-frame/div/split-page-layout/div/div/div[2]/div/div/div[2]/div[2]/div[1]/div/div[3]/div/div[2]/details/ul/li[2]/div/modal-dialog/div[2]/form/button",
        ).click()
        print("==== 确认 ====\n")
        time.sleep(4)

        num = num + 1
    except Exception:
        print("==== 共清理 %d 条记录 ====\n" % num)
        break

print("\n---- end ----\n")
browser.quit()
