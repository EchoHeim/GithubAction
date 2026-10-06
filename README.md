# GithubAction

用 GitHub Actions 托管一堆定时小任务：网站签到、天气预报、富途种子浇水、周报推送，
外加一套本地跑签到的 Selenium 工具。

## 入门

- [什么是 GitHub Actions](./GitHubActions入门.md)
- [Crontab 定时任务参考设置](https://crontab.guru/)

## 目录结构

```text
.github/workflows/     五个工作流，仓库的调度入口
Selenium/              Selenium 签到工具本体
  CheckIN/             各站点签到脚本 + 本地运行器
  CleanRuns/           批量删除历史 workflow run（CDP 版）
  Futu/                富途种子农场脚本
  base.py              环境检测、代理处理、图片验证码识别等公共代码
Messaging/             消息通知封装（钉钉 / 飞书 / 企微 / 邮件）
Trending/              GitHub 热榜 → DeepSeek 写稿 → 飞书推送
Weather/               wttr.in 取天气 + 邮件发送
```

## 1. 网站签到

工作流：`check_in.yml`（每天 22:22 UTC = 北京时间次日 6:22）

目前 Actions 里跑的站点：**V2EX、52pojie、掘金、NS中文网**。
也可以在 Actions 页手动触发时选站点（`all` / `v2ex` / `52pojie` / `juejin` / `ns211`）。

各站点脚本在 [`Selenium/CheckIN/`](./Selenium/CheckIN/README.md)：

| 脚本 | 站点 | 凭据方式 |
|---|---|---|
| `v2ex.py` | V2EX | 账号密码 + Cookie |
| `52pojie.py` | 吾爱破解 | **只能 Cookie**，登录页有人机验证，账号密码过不去 |
| `juejin.py` | 掘金 | 账号密码（自动过滑块），可选 Cookie 兜底 |
| `ns211.py` | NS中文网 | 用户名 + 密码，Secret 名是 `NS211_SECRET` |
| `aliyun.py` | 阿里云盘 | 账号密码，本地跑 |
| `fishpi.py` | 摸鱼派 | 账号密码 |

> **聚宽（`JoinQuant.py`）已移出 Actions**，托管 runner 出口 IP 在海外，会被地区风控直接拦掉。
> 改成在本机跑：`python Selenium/CheckIN/run_local.py joinquant`

脚本除了签到还会顺手做点别的（掘金抽矿石、发沸点、点赞收藏文章等），
每项都能用 `.env.local` 里的开关关掉，细节看 [`LOCAL_RUN.md`](./Selenium/CheckIN/LOCAL_RUN.md)。

本地跑：

```bash
# 凭据复制 .env.local.example 成 .env.local 填好，不会进仓库
python Selenium/CheckIN/run_local.py joinquant
python Selenium/CheckIN/run_local.py all
```

## 2. 富途种子

工作流：`futu_seed.yml`（每两小时一次）

自动给[富途种子](https://seed.futunn.com/?lang=zh-cn&panel=cultureroom)浇水、帮好友施肥。
脚本在 `Selenium/Futu/SeedFarm.py`。

## 3. 天气预报

工作流：`weather_bot.yml`（每天 21:00 UTC = 北京时间次日 5:00）

用 [wttr.in](https://wttr.in/) 取指定城市天气，邮件发给自己。脚本在 `Weather/`。

[详细说明](./Weather/README.md)

## 4. GitHub 热榜周报（Trending → DeepSeek → 飞书）

工作流：`trending_article.yml`（`cron: "0 22 * * 5"` = 周五 22:00 UTC = 周六 06:00 北京）

抓 GitHub 近一周热度最高的项目 → DeepSeek 从候选池里**自主选题**
（不无脑取榜首，按"大众可用 / 技术新颖 / 工具属性 / 能落地"打分）→ 拉 README 消化成
1500~2000 字推文 → 以 **.md 源文件**发到飞书。

模型固定 `deepseek-flash`（= DeepSeek-V4.1-Flash），**开启思考模式**。
飞书通道优先走**自建应用机器人**（直接发 `.md` 源文件，拿到就能排版），三项凭证没配齐
才回退到自定义机器人 webhook（发不了文件，只能发卡片）。**不落盘到仓库**，飞书是唯一出口——
推送失败脚本以退出码 1 结束，让 Actions 标红，避免"跑了但什么都没产出"被静默吞掉。

[详细说明](./Trending/README.md)

## 5. 清除历史 workflow run

脚本在 `Selenium/CleanRuns/`，两版：

- **`gh-del-runs.py`（推荐）** — 直连 CDP 驱动真实 Chrome，按界面按钮删。
  不用 token、不用密码，语义定位 + 每删一条校验总数 + 失败截图。
- **`CleanWorkflows.py`** — Selenium 版，账号密码登录走网页。慢（每条 5~8 秒），
  绝对 XPath 一改版就废，同样也不能在 Actions 里跑，只能本机手动。

```bat
cd Selenium/CleanRuns

:: 1. 起浏览器（首次手动登录一次 GitHub，登录态存 .browser-profile/）
start-browser.bat

:: 2. 试删 5 条
python run_local.py

:: 3. 满意后全量删（每个 workflow 留 20 条）
python run_local.py --full
```

> ⚠️ **删了不能恢复**，GitHub 没有回收站，第一次务必先 `--limit 5`。
> 根治办法是把 `Settings → Actions → General` 的 retention period 拉短。

[详细说明](./Selenium/CleanRuns/README.md)

## 6. 调试用：SSH 进 Actions runner

工作流：`ngrok_github.yml`（手动触发）

先故意跑一个不存在的脚本触发失败，再用 ngrok 起 SSH 隧道连进去看现场。
`NGROK_TOKEN` 和 `NGROK_SSH_PASSWD` 走仓库 Secrets。

## 7. 消息通知封装

`Messaging/` 下是几个通知通道的薄封装，被签到脚本直接 import：

| 文件 | 通道 |
|---|---|
| `DingTalk.py` | 钉钉自定义机器人 |
| `Feishu.py` | 飞书自定义机器人 |
| `WeCom.py` | 企业微信 |
| `E-Mail.py` | 邮件 |
| `Msg.py` | 统一入口，签到脚本只 import 这个 |

> 早期签到脚本会把结果推送到这些通道，现在大多改成汇总输出到终端了。
> 模块还在，`aliyun.py` 之类仍依赖它。