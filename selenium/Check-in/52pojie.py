# -*- coding: UTF-8 -*-

import sys 
sys.path.append("..") 

from base import *

# username = sys.argv[1] # 登录账号
# password = sys.argv[2] # 登录密码

username = '416604093@qq.com'
password = 'China1995'

img_path = os.getcwd() + "/1.png"

@retry(stop_max_attempt_number=5)
def Breakdown52():
    try:
        driver = get_web_driver()
        driver.get("https://www.52pojie.cn/")
        driver.find_element_by_xpath("//*[@id='nameOrEmail']").send_keys(username)
        driver.find_element_by_xpath("//*[@id='loginPassword']").send_keys(password)
        driver.find_element_by_xpath("//*[@class='green']").click()

        driver.find_element_by_xpath("//*[@id='yesterday']").click()
        print('52pojie 签到成功')
    except:
        raise
    finally:
        driver.quit()

if __name__ == '__main__':
    Breakdown52()
