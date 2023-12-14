# -*- coding: UTF-8 -*-

import sys

sys.path.append("..")

from base import *

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

img_path = os.getcwd() + "/1.png"


@retry(stop_max_attempt_number=5)
def Breakdown52():
    try:
        driver = get_web_driver()
        driver.get("https://www.52pojie.cn/")

        # browser.find_element(By.XPATH,'//*[@id="loginFormWrapper"]/form/ul/li[3]/input').send_keys(password)

        driver.find_element(By.XPATH, "//*[@id='ls_username']").send_keys(username)
        driver.find_element(By.XPATH, "//*[@id='ls_password']").send_keys(password)
        driver.find_element(By.XPATH, "//*[@class='pn vm']").click()

        driver.find_element(By.XPATH, "//*[@id='yesterday']").click()
        print("52pojie 签到成功")
    except:
        print("52pojie 签到shib")
        # raise
    finally:
        print("52pojie签到shib")
        # driver.quit()


if __name__ == "__main__":
    Breakdown52()
