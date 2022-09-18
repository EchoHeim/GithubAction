# -*- coding: UTF-8 -*-

import sys

from ChromeSelenium.base import *
from WeCom import *

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

# 富途牛牛 种子农场 登录地址
website='https://passport.futunn.com/?target=https%3A%2F%2Fseed.futunn.com%2F%3Flang%3Dzh-cn%26panel%3Dcultureroom#login'

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)

browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/ul/li[2]/input').send_keys(username)            # 输入账号
browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/ul/li[3]/input').send_keys(password)            # 输入密码
browser.find_element(By.XPATH,'/html/body/div[1]/div[2]/div[4]/form/ul/li[5]/div[1]/label/span').click()        # 勾选协议
browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/input[4]').click()        # 点击登录
time.sleep(8)
print(browser.title)

WeCom_SendMsg("HuangShiLong","种子已成熟，需要重新播种！")

num=browser.find_element(By.XPATH,'//*[@class="opBtn waterBtn ng-scope"]').text
if num == 0:
    print("\n==== 种子已经喝饱了，不需要再浇水！ ====\n")
else:
    try:
        # num=num-1
        # print("\n==== 给自己浇水, 剩余 %d 次 ====\n" % int(num))
        print("\n==== 给自己浇水 ====\n")
        browser.find_element(By.XPATH,'//*[@class="waterCanvas"]').click()
    except:
        WeCom_SendMsg("HuangShiLong","种子已成熟，需要重新播种！")
        print("\n==== 种子已成熟，需要重新播种！ ====\n")

time.sleep(4)

print("==== 进入好友列表 ====\n")
browser.find_element(By.XPATH,'/html/body/div[1]/div/div[8]/ul/li[3]/a').click()
time.sleep(4)
print("==== 筛选 (可施肥) ====\n")
browser.find_element(By.XPATH,'//*[@class="filter-op"]/span').click()
time.sleep(2)

for i in range(0,40):
    try:
        browser.find_element(By.XPATH,'//*[@class="can_fert icon_friends-fert"]').click()   # 选中一位好友
        time.sleep(4)
        browser.find_element(By.XPATH,'//*[@class="opIcon icon_fert"]').click()         # 浇水
        time.sleep(4)
        browser.find_element(By.XPATH,'//*[@class="back-home"]/span').click()           # 返回好友列表
        time.sleep(4)
    except:
        print ("==== 施肥成功 %d 好友 ====" % i)
        break
        
print ("\n---- end ----\n")
browser.quit()
