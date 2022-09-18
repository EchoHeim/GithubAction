# -*- coding: UTF-8 -*-

import sys 
sys.path.append("..") 

from base import *

username = sys.argv[1] # 登录账号
password = sys.argv[2] # 登录密码


def fishpi():
    try:
        driver = get_web_driver()
        driver.get("https://fishpi.cn/login?goto=https%3A%2F%2Ffishpi.cn%2F")

        driver.find_element(By.XPATH,'//*[@autofocus="autofocus"]').send_keys(username)
        driver.find_element(By.XPATH,'//*[@type="password"]').send_keys(password)
        driver.find_element(By.XPATH,"/html/body/div[3]/div/div[1]/div/button[1]").click()
        time.sleep(4)

        driver.find_element(By.XPATH,"//*[@id='yesterday']").click()

        
        driver.get('https://v2ex.com/mission/daily')
        driver.find_element(By.XPATH,"//*[@type='button']").click()

        print('fishpi - 签到成功')
    except:
        raise
    finally:
        driver.quit()

if __name__ == '__main__':
    fishpi()
