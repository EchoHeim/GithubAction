# -*- coding: UTF-8 -*-

import sys

from ChromeSelenium.base import *
from Messaging.Msg import *

username = sys.argv[1]  # 登录账号
password = sys.argv[2]  # 登录密码

img_path = os.getcwd() + "/test.png"


# @retry(stop_max_attempt_number=5)
def v2ex():
    try:
        driver = get_web_driver()
        driver.get("https://v2ex.com/signin")

        driver.find_element(By.XPATH, '//*[@placeholder="用户名或电子邮件地址"]').send_keys(
            username
        )
        driver.find_element(By.XPATH, '//*[@type="password"]').send_keys(password)

        valid = Ocr_Captcha(
            driver, "//input[starts-with(@style,'background-image')]", img_path
        )  # 验证码识别
        time.sleep(5)
        driver.find_element(
            By.XPATH, "//*[@placeholder='请输入上图中的验证码，点击可以更换图片']"
        ).send_keys(valid)
        time.sleep(4)
        driver.find_element(By.XPATH, "//*[@type='submit']").click()
        print("===> v2ex 登录")

        time.sleep(4)
        driver.get("https://v2ex.com/mission/daily")
        driver.find_element(By.XPATH, "//*[@type='button']").click()
    except:
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    v2ex()
