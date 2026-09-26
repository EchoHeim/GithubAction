# 本机运行签到脚本

GitHub Actions 的托管 runner 出口 IP 在海外，而聚宽只对大陆 IP 开放 ——
网页入口会被替换成「当前地区暂不支持访问」，后面所有元素定位跟着全崩。
把聚宽这一步搬到本机跑就能绕开，脚本本身一行都不用改。

## 一次性准备

**1. 虚拟环境**（已建好，无需重装）

```
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin
```

依赖版本与线上 CI 跑通的组合一致（selenium 4.49.0 / ddddocr 1.6.1 / opencv-python 5.0.0.93）。
万一环境损坏，重建方式：

```bat
"C:\Users\Lodge\AppData\Local\Programs\Python\Python314\python.exe" -m venv "C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin"
"C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe" -m pip install selenium==4.49.0 ddddocr==1.6.1 opencv-python==5.0.0.93 numpy==2.5.3 pillow==12.3.0 requests==2.34.2 retrying==1.4.2 -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**2. 凭据**（必须做，否则跑不起来）

`.env.local` 已在 `.gitignore` 里，不会进仓库。填入与 GitHub Secrets 相同的值：

```ini
JQ_USERNAME=聚宽账号
JQ_PASSWORD=聚宽密码
FEISHU_BOT_ID=飞书机器人 ID
CHECKIN_HEADLESS=1
```

## 跑起来

手动跑一次（能看到浏览器和实时输出）：

```bat
ChromeSelenium\Check-in\run_local.bat
```

或者直接调 Python：

```bash
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B ChromeSelenium/Check-in/run_local.py
```

## 登录态与风控（重要）

聚宽有**自研的拼图滑块风控**，登录和签到都可能弹（触发时登录接口返回 `code=105`）。
所以本机运行做了两件事：

1. **固定浏览器 profile**：`ChromeSelenium/Check-in/.browser-profile/`。
   Chrome 用它启动，登录 cookie 留在里面，第二天跑的时候直接复用，**不用重新登录**。
   （该目录已在 `.gitignore` 里 —— 里面有你的登录 cookie，别提交。）
2. **首次运行需要你盯一下**：第一次跑会真的登录一次。如果弹出滑块验证码
   （`#yth_captchar`），手动拖过去即可 —— 那一次的登录态会被存下来。

想从头来过（比如怀疑 cookie 失效），删掉 profile 目录再跑：

```bat
rmdir /s /q "ChromeSelenium\Check-in\.browser-profile"
```

> **已知限制**：如果**签到动作本身**弹滑块，当前脚本不会自动识别 —— 日志里会看到签到失败。
> 这种情况需要再补一层 OpenCV 缺口识别 + 模拟拖动（`lzwme/ql-scripts` 的
> `ql_joinquant_checkin.py` 里有成熟实现可移植）。先跑一次看日志，确认到底弹不弹再决定。

## 每日定时

已注册计划任务 `JoinQuantCheckIn`，每天 **06:22**（对齐线上 CI 的北京时间），
由 `pythonw.exe` 静默启动，不弹控制台窗口。关机错过会开机后补跑。

```
查看 / 修改：任务计划程序 → 任务计划程序库 → JoinQuantCheckIn
临时停用  ：Disable-ScheduledTask -TaskName JoinQuantCheckIn
彻底删除  ：Unregister-ScheduledTask -TaskName JoinQuantCheckIn -Confirm:$false
```

> 注：本机安全策略拉黑了 `schtasks.exe`、`wscript.exe` 这类 LOLBin，
> 所以任务是用 `Register-ScheduledTask` 注册的，别指望用 schtasks 改。

## 日志

每次运行同时打印到控制台并落盘：

```
ChromeSelenium/Check-in/logs/joinquant-YYYY-MM-DD.log
```

跑完最后一行会给结论（是否检测到失败标记），失败时附上对应的原文。

## 踩过的坑（都已在代码里处理）

| 现象 | 原因 | 处理位置 |
|---|---|---|
| `WebDriverException: unhandled request` | 本机 shell 的 `http_proxy` 被 Selenium 套到了发往 chromedriver 的请求上 | `run_local.py` 启动子进程前清空代理变量 |
| `Invalid URL 'xxx'` | 飞书机器人 ID 像是 URL | 正常现象，用错 ID 才会出现 |
| 日志顺序错乱 | 子进程 stdout 走块缓冲，traceback 先冒出来 | 子进程加 `-u` |
| `pythonw` 下 `print` 直接抛异常 | 无控制台时 `sys.stdout` 是 `None` | 回退到 `os.devnull` |
| 每天弹一个浏览器窗口 | Windows 分支默认有头 | `.env.local` 里 `CHECKIN_HEADLESS=1` |

## 搬到 Linux 服务器上跑（备选）

同样的脚本可以直接用，差异只有三处：

1. **cron 按本地时间排** —— 线上那个 `22 22 * * *` 是 UTC，等于北京 06:22；
   服务器上要写 `22 6 * * *`，直接抄数字会提前 8 小时。
2. **chromedriver 路径** —— `base.py` 的 Linux 分支硬编码 `/usr/bin/chromedriver`。
3. **系统依赖** —— `opencv-python` 需要 `libgl1` 和 `libglib2.0-0`。

```bash
22 6 * * * cd /path/to/GithubAction && /path/to/python -u ChromeSelenium/Check-in/run_local.py >> ChromeSelenium/Check-in/logs/cron.log 2>&1
```

## 线上怎么办

GitHub Actions 那边的聚宽步骤已经跑不通了（出口 IP 决定，改代码没用）。
建议从 `.github/workflows/check_in.yml` 里摘掉 `Check in JoinQuant` 这一步，
省得每天推一张假的失败卡片。其余站点（v2ex / fishpi / futu / weather）不受影响，原样留在 Actions 即可。
