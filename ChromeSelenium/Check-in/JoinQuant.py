# -*- coding: UTF-8 -*-

import sys
sys.path.append("..")

from base import *

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

website='https://www.joinquant.com/user/login/index?type=login'

def joinquant():
    try:
        browser = get_web_driver()
        browser.get(website)
        time.sleep(4)
        print(browser.title)

        browser.find_element(By.XPATH,'//*[@class="phone pwd-phone"]').send_keys(username)
        browser.find_element(By.XPATH,'//*[@class="jq-login__password"]').send_keys(password)
        browser.find_element(By.XPATH,'//*[@class="login-submit btnPwdSubmit"]').click()        # 点击登录
        time.sleep(4)
        print(browser.title)

        # 点击 积分 页
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]').click()
        time.sleep(4)
        browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素

        # 签到
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[2]/div[2]/div[2]/div/button').click()
        print('---> JoinQuant 签到成功!')
        time.sleep(2)

        # 进入社区页面
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/a/button').click()
        browser.switch_to.window(browser.window_handles[1])  # 切换页面
        print('==== 进入社区页面 ====')
        time.sleep(4)
        print(browser.title)

        # 浏览文章
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[1]/div[2]/div[1]/div[4]/div/div[1]/div[1]').click()
        browser.switch_to.window(browser.window_handles[2])  # 切换页面
        print('==== 浏览文章 ====')
        time.sleep(4)
        browser.refresh()   # 刷新页面
        time.sleep(4)
        browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
        print(browser.title)

        browser.switch_to.window(browser.window_handles[0])  # 切换回第一个页面
        print('==== 返回积分主页 ====')
        browser.refresh()   # 刷新页面
        time.sleep(4)

        # 点击 积分 页
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]').click()
        time.sleep(2)
        browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
        
        # 领取积分
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/button').click()
        print('---> JoinQuant 积分领取成功!')
        time.sleep(4)

    except:
        print('===> JoinQuant 签到失败!')
    finally:
        browser.quit()

def joinquant_get():
    try:
        browser = get_web_driver()
        browser.get(website)
        time.sleep(4)
        print(browser.title)

        browser.find_element(By.XPATH,'//*[@class="phone pwd-phone"]').send_keys(username)
        browser.find_element(By.XPATH,'//*[@class="jq-login__password"]').send_keys(password)
        browser.find_element(By.XPATH,'//*[@class="login-submit btnPwdSubmit"]').click()        # 点击登录
        time.sleep(4)
        print(browser.title)

        # 点击 积分 页
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[2]/div[1]/div[2]').click()
        time.sleep(4)
        browser.execute_script("window.scrollBy(0,400)")  # 向下滑动400个像素
        
        # 领取积分
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[1]/div[1]/div[2]/div[2]/div/button').click()
        print('---> JoinQuant 积分领取成功!')
        time.sleep(4)

    except:
        print('===> JoinQuant 积分领取失败!')
    finally:
        browser.quit()


if __name__ == '__main__':
    joinquant()
    # joinquant_get()
