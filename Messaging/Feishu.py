#! /usr/bin/env python3
# -*- coding: UTF-8 -*-

from contextlib import redirect_stderr

import requests
import json


# 发送普通消息，ID 是自定义机器人的 webhook
def Feishu_SendMsg(ID, Obj, Status, Msg):
    url = ID
    header = {"Content-type": "application/json", "charset": "utf-8"}
    data = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": Obj,
                    "content": [
                        [
                            {"tag": "text", "text": Status},
                            {
                                "tag": "text",
                                "text": Msg,
                            },
                            # {"tag": "at", "user_id": "EchoHeim"},
                        ]
                    ],
                }
            }
        },
    }
    msg_encode = json.dumps(data, ensure_ascii=True).encode("utf-8")

    return requests.post(url, data=msg_encode, headers=header)


# 发送卡片消息，支持 markdown 基本语法。ID 是自定义机器人的 webhook
def Feishu_SendCardMsg(ID, title, content):
    # 构建卡片消息内容
    message = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}}
            ],
        },
    }

    # 发送消息到飞书机器人
    response = requests.post(ID, json=message)

    if response.status_code == 200:
        print("消息发送成功！")
    else:
        print(f"消息发送失败！错误代码: {response.status_code}")
