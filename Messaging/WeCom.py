#! /usr/bin/env python3
# -*- coding: UTF-8 -*-

import json
import time
import requests, sys

"""
通过企业微信应用给企业成员发消息
"""


class WeChatPub:
    msg = requests.session()

    def __init__(self):
        self.CORP_ID = "ww77ce342be63ff1fb"  # 企业号的标识
        self.SECRET = "wZ9yUpUuzkXK2BI3aiU6ectsdKavuOES6m4cUOMi7bI"  # 管理组凭证密钥
        self.AGENT_ID = 1000002  # 应用ID
        self.token = self.get_token()

    def get_token(self):
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        data = {"corpid": self.CORP_ID, "corpsecret": self.SECRET}
        req = requests.get(url=url, params=data)
        res = req.json()
        return res["access_token"] if res["errmsg"] == "ok" else res

    def send_msg(self, receiver, content):
        URL = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={self.token}"
        header = {"Content-Type": "application/json"}
        form_data = {
            "touser": receiver,  # 接收人
            # "toparty": "1",               # 接收部门
            # "totag": " TagID1 | TagID2 ", # 通讯录标签id
            "msgtype": "textcard",
            "agentid": self.AGENT_ID,  # 应用ID
            "textcard": {
                "title": "Github Actions Notice!",
                "description": content,
                "url": URL,
                "btntxt": "更多",
            },
            "safe": 0,
        }
        rep = self.msg.post(
            url=URL, data=json.dumps(form_data).encode("utf-8"), headers=header
        )
        res = rep.json()
        if res["errmsg"] == "ok":
            print("send message succeed")
            return "send message succeed"
        else:
            print("send message error", res)
            return res


def WeCom_SendMsg(Obj, Msg):
    wechat = WeChatPub()
    timenow = time.strftime(" %Y-%m-%d %H:%M:%S ", time.localtime())
    wechat.send_msg(
        Obj,
        f'<div class="gray"> {timenow} </div> <div class="normal"> ==== 温馨提醒! ==== </div> <div class="highlight"> {Msg} </div>',
    )
