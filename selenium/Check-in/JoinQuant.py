# -*- coding: UTF-8 -*-

import sys
sys.path.append("..")

from base import *

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码

# username = "17606536286" # 登录账号
# password = "China1995" # 登录密码

website='https://www.joinquant.com/user/login/index?type=login'

@retry(stop_max_attempt_number=5)
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
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[2]/div[2]/div[2]/div[2]/div/a/button').click()
        print('---> JoinQuant 签到成功!')
        time.sleep(2)

        # 进入社区页面
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[2]/div[1]/div[2]/div[2]/div/a/button').click()
        print('==== 进入社区页面 ====')
        time.sleep(4)

        # 浏览文章
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[2]/div[1]/div[2]/div[1]/div[4]/div/div[1]/div[1]').click()
        print('==== 浏览文章 ====')
        time.sleep(4)

        # 返回主页领取积分
        browser.switch_to.window(browser.window_handles[0])  # 切换回第一个页面
        print('==== 返回积分主页 ====')
        browser.refresh()   # 刷新页面
        time.sleep(4)

        # 领取积分
        browser.find_element(By.XPATH,'/html/body/section/main/div/div[3]/div/div[2]/div[2]/dl/dd[2]/div[1]/div[2]/div[2]/div/button').click()
        print('---> JoinQuant 积分领取成功!')
        time.sleep(4)

    except:
        print('===> JoinQuant 签到失败!')
    finally:
        time.sleep(2)
        browser.quit()

if __name__ == '__main__':
    joinquant()
