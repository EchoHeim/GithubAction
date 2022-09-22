# -*- coding: UTF-8 -*-

import sys

from ChromeSelenium.base import *
from Messaging.Msg import *

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

website='https://www.joinquant.com/user/login/index?type=login'

browser = get_web_driver()
browser.get(website)
time.sleep(4)
print(browser.title)

str = "## JoinQuant "

try:
    browser.find_element(By.XPATH,'//*[@class="phone pwd-phone"]').send_keys(username)
    browser.find_element(By.XPATH,'//*[@class="jq-login__password"]').send_keys(password)
    browser.find_element(By.XPATH,'//*[@class="login-submit btnPwdSubmit"]').click()        # 点击登录
    time.sleep(4)
    print(browser.title)
except:
    print('\n===> JoinQuant 登录失败!')
    str = str + "\n > ---- 登录失败! ----"

# 显示当前积分
try:
    browser.refresh()   # 刷新页面
    time.sleep(10)
    num=browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]/span').text
    print('\n---> JoinQuant: 当前积分 %d \n' % int(num))
    str = str + "\n > <font color=#fc6315> 昨日积分: </font>" + str(num) + " "
except:
    print('\n===> Err: < 显示当前积分 >')
    str = str + "\n > ---- 无法显示积分! ----"
    
try:
    # 点击 积分 页
    browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]').click()
    time.sleep(4)
    # 签到
    browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[2]/div[2]/div[2]/div/button').click()
    time.sleep(2)
except:
    print('\n===> JoinQuant 签到失败!')
    str = str + "\n > ---- 签到失败! ----"

try:
    # 进入社区页面
    browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/a/button').click()
    browser.switch_to.window(browser.window_handles[1])  # 切换页面
    time.sleep(4)
    print(browser.title)
except:
    print('\n===> Err: < 进入社区页面 >')
    str = str + "\n > ---- 无法进入社区页面! ----"

try:
    # 浏览文章
    browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[1]/div[2]/div[1]/div[4]/div/div[1]/div[1]').click()
    browser.switch_to.window(browser.window_handles[2])  # 切换页面
    time.sleep(4)
    browser.refresh()   # 刷新页面
    time.sleep(4)
    browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
    print(browser.title)
except:
    print('\n===> Err: < 浏览文章 >')
    str = str + "\n > ---- 无法浏览文章! ----"

browser.switch_to.window(browser.window_handles[0])  # 切换回第一个页面
print('\n==== 返回积分主页 ====')
time.sleep(40)
browser.refresh()   # 刷新页面
time.sleep(4)

# 点击 积分 页
browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]').click()
time.sleep(2)
browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素

# 领取积分
try:
    browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/button').click()
    time.sleep(4)
except:
    print('\n===> JoinQuant 积分领取失败!')
    str = str + "\n > ---- 积分领取失败! ----"

# 显示当前积分
try:
    browser.refresh()   # 刷新页面
    time.sleep(10)
    num=browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]/span').text
    print('\n---> JoinQuant: 当前积分 %d \n' % int(num))
    str = str + "\n > <font color=#fc6315> 当前积分: </font>" + str(num) + " "
except:
    print('\n===> Err: < 显示当前积分 >')
    str = str + "\n > ---- 无法显示积分! ----"

DingTalk_SendMsg("GitAction",str)

# 退出Chrome
browser.quit()
