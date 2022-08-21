# python 3.8
import time
import datetime
import hmac
import hashlib
import base64
import urllib.parse

import requests
from bs4 import BeautifulSoup


# 定义爬虫类
class Spider():
    def __init__(self):
        self.url = 'https://www.baidu.com/s?wd=%E4%B8%8A%E8%AF%81%E6%8C%87%E6%95%B0&rsv_spt=1&rsv_iqid=0xcb2b2b7900123bc0&issp=1&f=8&rsv_bp=1&rsv_idx=2&ie=utf-8&rqlang=cn&tn=baiduhome_pg&rsv_enter=1&rsv_dl=tb&rsv_btype=t&inputT=44370&rsv_t=2db0u4wroxTjyaiDfH3fWAevboNoEOf%2FJjR94bKGb2RpwUSfzUI5gxlN%2BBT%2BoS4zPKnH&oq=python%2520%25E7%2588%25AC%25E5%258F%2596%25E6%258C%2587%25E6%2595%25B0&rsv_pq=d409a223000c97e0&rsv_sug3=79&rsv_sug1=73&rsv_sug7=101&rsv_sug2=0&rsv_sug4=45526/'

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.77 Safari/537.36'
        }
        r = requests.get(self.url, headers=self.headers)
        r.encoding = r.apparent_encoding
        self.html = r.text

    def Url(self):
        timestamp = str(round(time.time() * 1000))
        secret = 'SECf2b70ca8b507e2ae1e7cf476f3e75fadb8ee869ab34bed495eb361d5155c0865'
        secret_enc = secret.encode('utf-8')
        string_to_sign = '{}\n{}'.format(timestamp, secret)
        string_to_sign_enc = string_to_sign.encode('utf-8')
        hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        print(timestamp)
        print(sign)
        self.dingdingurl = "https://oapi.dingtalk.com/robot/send?access_token=cad451762de13cc3c67275fe9e939ea3f58cca657a3cac94faedb220952df0a7" + "&timestamp=" + timestamp + "&sign=" + sign;

    def send(self):
        curTime = (datetime.datetime.now() + datetime.timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
        print(curTime)
        data = {
            "msgtype": "text",
            "text": {"content": curTime +" 上证指数："+self.text},
            "at": {
                # "atMobiles": [
                #     "156xxxx8827",
                #     "189xxxx8325"
                # ],
                "isAtAll": 'true'
            }
        }
        r = requests.post(self.dingdingurl, json=data)
        print(r)

    def BeautifulSoup_find(self):
        '''用BeautifulSoup解析'''
        soup = BeautifulSoup(self.html, 'lxml')  # 转换为BeautifulSoup的解析对象()里第二个参数为解析方式
        index = soup.find('div', class_='op-stockdynamic-moretab-cur').contents[1].string
        percent = soup.find('div', class_='op-stockdynamic-moretab-cur').contents[4].string
        print(index + ' |percent: ' + percent)
        self.text = index + ' |percent: ' + percent


if __name__ == '__main__':
    spider = Spider()
    spider.BeautifulSoup_find()
    spider.Url()
    spider.send()
