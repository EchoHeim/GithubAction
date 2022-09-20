#coding:utf-8

import yagmail as autosend_mail

from loguru import logger

# 读取文件到列表
with open("ip.txt","r") as ip_file:
    array = []
    content = ip_file.read().splitline()
    for line in ip_file:
        array.append(line)


# 邮件发送
# 发件人信息;(邮箱、密码、服务器)
self_server = autosend_mail.SMTP(user="shilong_native@163.com", password="OPTZKTAEHISSJQOB", host="smtp.163.com")      

email_Name = ["416604093@qq.com"]           # 收件人;
# email_Title = ["demo"]                    # 邮件标题;(非必需)
email_Title = content
email_Content = array                       # 邮件内容;(非必需)
email_Annexes = ["ip.txt"]                  # 邮件附件;(非必需)

self_server.send(to=email_Name, subject=email_Title, contents=email_Content, attachments=email_Annexes)
self_server.close()

logger.info("\n**** Email is sent! ****\n")
