# -*- coding: UTF-8 -*-

from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC

import platform
import traceback
import os, sys, time

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

# 富途牛牛 种子农场 登录地址
website='https://passport.futunn.com/?target=https%3A%2F%2Fseed.futunn.com%2F%3Flang%3Dzh-cn%26panel%3Dcultureroom#login'

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--headless')
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--disable-dev-shm-usage')

print("==== 检测环境 ====")
if platform.system() == 'Windows':
    print('\nCurrent Operating System: ==== Windows ====\n')
    browser = webdriver.Chrome('chromedriver.exe')

elif platform.system() == 'Linux':
    print('\nCurrent Operating System: ==== Linux ====\n')
    chromedriver = "/usr/bin/chromedriver"
    os.environ["webdriver.chrome.driver"] = chromedriver
    browser = webdriver.Chrome(chrome_options=chrome_options,executable_path=chromedriver)

browser.get(website)
time.sleep(2)
print(browser.title)

browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/ul/li[2]/input').send_keys(username)            # 输入账号
browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/ul/li[3]/input').send_keys(password)            # 输入密码
browser.find_element(By.XPATH,'/html/body/div[1]/div[2]/div[4]/form/ul/li[5]/div[1]/label/span').click()        # 勾选协议
browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/input[4]').click()        # 点击登录
time.sleep(2)
print(browser.title)

print("\n==== 给自己浇水 ====\n")
browser.find_element(By.XPATH,'//*[@class="waterCanvas"]').click()          
time.sleep(4)

print("\n==== 进入好友列表 ====\n")
browser.find_element(By.XPATH,'/html/body/div[1]/div/div[8]/ul/li[3]/a').click()
time.sleep(4)
print("\n==== 筛选 (可施肥) ====\n")
browser.find_element(By.XPATH,'//*[@class="filter-op"]/span').click()
time.sleep(2)

for i in range(1,20):
    try:
        browser.find_element(By.XPATH,'//*[@class="can_fert icon_friends-fert"]').click()   # 选中一位好友
        time.sleep(4)
        browser.find_element(By.XPATH,'//*[@class="opIcon icon_fert"]').click()         # 浇水
        time.sleep(4)
        browser.find_element(By.XPATH,'//*[@class="back-home"]/span').click()           # 返回好友列表
        time.sleep(4)
        print ("\n==== 施肥成功 %d 好友 ====\n" % i)
    except:
        break
        
print ("\n---- end ----\n")        
browser.quit()
