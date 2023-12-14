#! /usr/bin/env python3
# -*- coding: UTF-8 -*-

import time, hmac, hashlib, base64
import urllib.parse
import urllib.request
import datetime
import json

timestamp = str(round(time.time() * 1000))
secret = "SECb4ae08d96611cb9e115a4f51c3378be17cd3bc3bf1e35b87a11c44126c15b229"
secret_enc = secret.encode("utf-8")
string_to_sign = f"{timestamp}\n{secret}"
string_to_sign_enc = string_to_sign.encode("utf-8")
hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))

url_token = f"https://oapi.dingtalk.com/robot/send?access_token=38d45d1bd56eafcb5e16b9356519bb5425490894805c7e1578bada250ae51034&timestamp={timestamp}&sign={sign}"


def send_request(url, datas):
    header = {"Content-Type": "application/json", "Charset": "UTF-8"}
    sendData = json.dumps(datas)
    sendDatas = sendData.encode("utf-8")
    request = urllib.request.Request(url=url_token, data=sendDatas, headers=header)
    opener = urllib.request.urlopen(request)

    # 输出响应结果
    print(opener.read())


def get_string():
    """
    想要发送的内容,注意消息格式,如果选择 markdown,字符串中应为包含Markdown格式的内容
    """
    return "## GithubAction \n <font color=#00ffff>测试信息！</font>"


def DingTalk_SendMsg(Obj, Msg):  # sourcery skip: avoid-builtin-shadow
    dict = {
        "msgtype": "markdown",
        "markdown": {"title": Obj, "text": Msg},
        "at": {"isAtAll": False},  # isAtAll：是否@所有人
    }
    send_request(url_token, dict)
