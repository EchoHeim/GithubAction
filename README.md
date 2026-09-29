# GithubAction

## 入门介绍

- [什么是GithubAction](./GitHubActions入门.md)

- [Crontab定时任务参考设置](https://crontab.guru/)

## 1. selenium 自动化

> 使用 chrome，[环境部署](https://github.com/EchoHeim/GithubAction/blob/master/Selenium/README.md)

- 测试

    环境搭建好之后可以使用 test.py 脚本进行测试，在 GithubAction 目录下执行 `python.exe .\Selenium\test.py` 会弹出浏览器进入百度首页，等待4秒后，终端会打印网页主题。

- 网站签到

    - [聚宽JoinQuant](https://www.joinquant.com/view/user/floor?type=mainFloor)
    - [摸鱼派](https://fishpi.cn/)
    - [v2ex论坛](https://v2ex.com/member/MacLodge)

- [富途种子](https://seed.futunn.com/?lang=zh-cn&panel=cultureroom)

    自动浇水，帮好友施肥

- 清除工作流日志

    两个版本，用途不同：

    - **CleanWorkflowsApi.py（推荐）** — 走 GitHub REST API，并发删除。
      公开仓库**列记录不需要 token**，删除需要一个带 `Actions: Read and write` 的 token。
      868 条记录几分钟就完事。

        ```bash
        # 只看会删哪些（免 token，立刻可用）
        python Selenium/CleanWorkflowsApi.py --dry-run

        # 真删：token 写进 Selenium/.env.local 的 GITHUB_TOKEN
        python Selenium/CleanWorkflowsApi.py --delete
        python Selenium/CleanWorkflowsApi.py --delete --keep 200 --max 50 --workers 8
        ```

        > 默认保留最新 100 条、预演不删，必须显式 `--delete`。
        > 注意代理方向和下面那版**相反**：API 调用要跟随环境代理（本机直连会被限流），
        > Selenium 那版反而必须清掉代理。

    - **CleanWorkflows.py** — 真浏览器逐条点删除。慢（每条 5~8 秒），
      但不需要 token，只用账号密码走网页登录。

        > 不能在 github actions 中自动运行，需本机手动跑，二次验证登录后自动删除工作流日志。

        本机跑法（凭据读同目录 `.env.local`，模板见 `.env.local.example`）：

        ```bash
        python Selenium/CleanWorkflows.py --dry-run
        python Selenium/CleanWorkflows.py --delete
        python Selenium/CleanWorkflows.py --delete --max 100
        ```

## 2. 天气预报信息

自动获取指定城市的天气状况，然后邮件发送给收件人

[详细说明](https://github.com/EchoHeim/GithubAction/blob/master/Weather/README.md)

## 3. GitHub 热榜周报（Trending → DeepSeek → 飞书）

**每周六早 6 点（北京时间）** 自动跑一次：抓 GitHub 近一周热度最高的项目 →
DeepSeek 从候选池里**自主选题**（不无脑取榜首，按"大众可用 / 技术新颖 / 工具属性 / 能落地"
打分）→ 拉 README 消化成 1500~2000 字的公众号推文 → 以 **.md 源文件**发到飞书。

模型固定 `deepseek-flash`（= DeepSeek-V4.1-Flash），**开启思考模式**。
飞书通道优先走**自建应用机器人**（直接发 `.md` 源文件，拿到就能排版），三项凭证没配齐
才回退到自定义机器人 webhook（发不了文件，只能发卡片）。**不落盘到仓库**，飞书是唯一出口——
推送失败脚本会以退出码 1 结束，让 Actions 标红，避免"跑了但什么都没产出"被静默吞掉。

工作流：[`.github/workflows/trending_article.yml`](./.github/workflows/trending_article.yml)
（`cron: "0 22 * * 5"` = 周五 22:00 UTC = 周六 06:00 北京）

[详细说明](./Trending/README.md)

## 参考项目

- [掘金滑动拼图验证码识别](https://github.com/shuai93/juejin)
- [图片验证码ocr](https://github.com/sml2h3/ddddocr)

- [钉钉开发文档](https://open.dingtalk.com/document/robots/custom-robot-access)
- [飞书开发文档](https://open.feishu.cn/document/client-docs/bot-v3/bot-overview)
- [飞书帮助中心](https://www.feishu.cn/hc/zh-CN/)
  