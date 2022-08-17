#coding=utf-8

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

import os
import platform

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

debug='false'

# 富途牛牛 种子农场 登录地址
website='https://passport.futunn.com/?target=https%3A%2F%2Fseed.futunn.com%2F%3Flang%3Dzh-cn%26panel%3Dcultureroom#login'

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--disable-dev-shm-usage')

if platform.system() == 'Windows':
    print('\nCurrent Operating System: ==== Windows ====\n')

    if debug == 'true':
        browser = webdriver.Chrome('chromedriver.exe')
    else:
        print('\n No debug mode!\n')

elif platform.system() == 'Linux':
    print('\nCurrent Operating System: ==== Linux ====\n')

    chromedriver = "/usr/bin/chromedriver"
    os.environ["webdriver.chrome.driver"] = chromedriver
    if debug == 'true':
        browser = webdriver.Chrome('chromedriver')
    else:
        browser = webdriver.Chrome(chrome_options=chrome_options,executable_path=chromedriver)

browser.get(website)
print(browser.title)




browser.quit()


