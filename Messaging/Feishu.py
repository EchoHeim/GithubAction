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
# 返回 True/False：调用方想确认「到底推没推出去」时能拿到结论；不接收返回值也不影响老用法。
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
    try:
        # 必须带 timeout：飞书偶发不响应，没超时会把整个签到 job 一路拖到 job 超时
        response = requests.post(ID, json=message, timeout=15)
    except requests.RequestException as err:
        print(f"消息发送失败！请求异常: {err}")
        return False

    if response.status_code == 200:
        # ⚠️ 飞书在 HTTP 200 里照样能回错误码（机器人被移出群、签名校验失败、频率超限……），
        # 只看状态码会把「没发出去」当成功，这是最坑的一种假成功。
        try:
            body = response.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and body.get("code") not in (0, None):
            print(f"消息发送失败！飞书返回 code={body.get('code')} msg={body.get('msg')}")
            return False
        print("消息发送成功！")
        return True

    print(f"消息发送失败！错误代码: {response.status_code} {response.text[:200]}")
    return False
