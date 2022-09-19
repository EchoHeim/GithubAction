#! /usr/bin/env python
# -*- coding: UTF-8 -*-

import time, hmac, hashlib, base64
import urllib.parse
import urllib.request
import datetime
import json

timestamp = str(round(time.time() * 1000))
secret = 'SECb4ae08d96611cb9e115a4f51c3378be17cd3bc3bf1e35b87a11c44126c15b229'
secret_enc = secret.encode('utf-8')
string_to_sign = '{}\n{}'.format(timestamp, secret)
string_to_sign_enc = string_to_sign.encode('utf-8')
hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
print(timestamp)
print(sign)

url = f'https://oapi.dingtalk.com/robot/send?access_token=38d45d1bd56eafcb5e16b9356519bb5425490894805c7e1578bada250ae51034&timestamp={timestamp}&sign={sign}'

def send_request(url, datas):
    header = {
        "Content-Type": "application/json",
        "Charset": "UTF-8"
    }
    sendData = json.dumps(datas)
    sendDatas = sendData.encode("utf-8")
    request = urllib.request.Request(url=url, data=sendDatas, headers=header)
    opener = urllib.request.urlopen(request)

    # 输出响应结果
    print(opener.read())

def get_string():
    '''
    自己想要发送的内容,注意消息格式,如果选择markdown,字符串中应为包含Markdown格式的内容
    '''
    str = "<font color=#00ffff>GitAction 昨日销售额:233</font> </br> <font color=#00ffff>昨日销量:XXX</font>"
    
    return str

def main():
    # isAtAll：是否@所有人
    dict = {
        "msgtype": "markdown",
        "markdown": {"title": "GitAction",
                     "text": ""
                     },
        "at": {
            "isAtAll": False
        }
    }

    #把文案内容写入请求格式中
    dict["markdown"]["text"] = get_string()
    send_request(url, dict)

if __name__ == '__main__':
    main()
