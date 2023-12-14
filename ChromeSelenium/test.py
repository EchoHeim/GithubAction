# -*- coding: UTF-8 -*-

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

import platform


def get_web_driver():
    service = Service()
    options = webdriver.ChromeOptions()
    if platform.system() == "Windows":
        print("\nCurrent Operating System: ==== Windows ====\n")
        # browser = webdriver.Chrome('chromedriver.exe')
        browser = webdriver.Chrome(service=service, options=options)
    elif platform.system() == "Linux":
        print("\nCurrent Operating System: ==== Linux ====\n")
        chromedriver = "/usr/bin/chromedriver"
        os.environ["webdriver.chrome.driver"] = chromedriver
        if "fv-az" in platform.node():  # github actions 服务器名
            chrome_options.add_argument(
                "--headless"
            )  # 浏览器不提供可视化页面. linux下如果系统不支持可视化不加这条会启动失败
        browser = webdriver.Chrome(
            chrome_options=chrome_options, executable_path=chromedriver
        )

    browser.implicitly_wait(10)  # 所有的操作都可以最长等待10s
    return browser


website = "https://www.baidu.com/"

driver = get_web_driver()

driver.get(website)

print(driver.title)
