# GithubAction

## 入门介绍

- [什么是GithubAction](./GitHubActions入门.md)

- [Crontab定时任务参考设置](https://crontab.guru/)

## 1. selenium 自动化

> 使用 chrome，[环境部署](https://github.com/EchoHeim/GithubAction/blob/master/ChromeSelenium/README.md)

- 测试

    环境搭建好之后可以使用 test.py 脚本进行测试，在 GithubAction 目录下执行 `python.exe .\ChromeSelenium\test.py` 会弹出浏览器进入百度首页，等待4秒后，终端会打印网页主题。

- 网站签到

    - [聚宽JoinQuant](https://www.joinquant.com/view/user/floor?type=mainFloor)
    - [摸鱼派](https://fishpi.cn/)
    - [v2ex论坛](https://v2ex.com/member/MacLodge)

- [富途种子](https://seed.futunn.com/?lang=zh-cn&panel=cultureroom)

    自动浇水，帮好友施肥

- 清除工作流日志
    - CleanWorkflows.py

        > 不能在 github actions 中自动运行，需手动指定仓库链接，二次验证登录后自动删除工作流日志。

## 2. 天气预报信息

自动获取指定城市的天气状况，然后邮件发送给收件人

[详细说明](https://github.com/EchoHeim/GithubAction/blob/master/Weather/README.md)

## 参考项目

- [掘金滑动拼图验证码识别](https://github.com/shuai93/juejin)
- [图片验证码ocr](https://github.com/sml2h3/ddddocr)

- [钉钉开发文档](https://open.dingtalk.com/document/robots/custom-robot-access)
- [飞书开发文档](https://open.feishu.cn/document/client-docs/bot-v3/bot-overview)
- [飞书帮助中心](https://www.feishu.cn/hc/zh-CN/)
  