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
Selenium\Check-in\run_local.bat
```

或者直接调 Python：

```bash
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/Check-in/run_local.py
```

## 跑其它站点（52pojie / 掘金）

`run_local.py` 支持用第一个参数选站点，不带参数就是聚宽（计划任务用的还是这条，没变）：

```bash
# 吾爱破解
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/Check-in/run_local.py 52pojie

# 掘金
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/Check-in/run_local.py juejin
```

各自的凭据在 `.env.local` 里填对应的一组：`PJ52_COOKIE`、
`JUEJIN_USERNAME/JUEJIN_PASSWORD`。
日志分别落 `logs/52pojie-YYYY-MM-DD.log`、`logs/juejin-YYYY-MM-DD.log`。

### 52pojie 的 Cookie 怎么取（**唯一的路**，2026-09-28 定稿）

**别用账号密码**（脚本里这条路径已经删掉了）—— 登录页挂着 Cloudflare Turnstile
（站点把它包成「点击验证」），而**本机线路根本连不上** Cloudflare：
`challenges.cloudflare.com` 域名能解析，但 443 端口连接 10 秒超时（`curl` 返回 000），
所以验证码组件加载不出来，服务端会回「抱歉，验证码填写错误」。
2026-09-26 无头/有头都试过、2026-09-28 又量了线路，确认不是选择器问题，改代码没用。

所以用**登录态 Cookie**：

1. 用你自己的浏览器正常登录 <https://www.52pojie.cn/>；
2. F12 → **Application** → 左侧 Storage 树里点 **Cookies** → 点 `https://www.52pojie.cn`；
3. 站点 cookie 前缀是 **`htVC_2132_`**（2026-09-27 从站点 Set-Cookie 实测），关键三项：
   `htVC_2132_auth`（最关键，代表登录态）、`htVC_2132_saltkey`、`htVC_2132_sid`；
   如果列表里还有 `wzws_sid`（WAF 的），一并带上更好。拼成一行：
   ```
   PJ52_COOKIE=htVC_2132_saltkey=xxxxx; htVC_2132_auth=yyyyy; htVC_2132_sid=zzzzz
   ```
   （也可以把整行 Cookie 头直接粘进去，脚本自己按 `;` 拆，多的项不影响）
4. ⚠️ 如果 Cookies 表格里 `htVC_2132_auth` 的 **HttpOnly 列是 ✓**，JS 的 `document.cookie`
   读不到它 —— 这时别用 Console 那招，改从 **Network → 刷新 → 点 Document 请求 →
   Request Headers 里的 `cookie:` 整行**（或右键请求 → Copy as cURL）里取，那份一定完整。
5. 有效期跟 Discuz 会话走，`cookietime=1` 时约一个月。日志里出现
   `注入的 Cookie 无效或已过期` 就重新抄一次。

> **2026-09-27 实测通过**（本机、Cookie 23 项）：
> `Cookie 登录态有效` → WAF 图片验证码过了 3 轮（前两张 OCR 认错，换图重试，上限 8 轮）
> → 任务页回执「恭喜您，任务已完成，关注论坛微信…一键签到送论坛币」→ 判为 `签到成功`，退出码 0。
> 注意 `home.php?mod=task&do=apply&id=2` 成功后站点会跳到 `do=draw&id=2` 那页，
> 回执文案里带「恭喜」，正好命中 `TASK_DONE_MARKERS`。

### 回帖（默认开）+ 卡片里的积分

签到之后脚本会去『精品软件区』（fid=16）**随机挑一个普通帖**（跳过置顶/公告），
在快捷回复框里发一条 `谢谢分享~`，并把**当前积分**（页头 `#extcreditmenu`）和回帖结果
一起写进飞书卡片。相关开关：

```ini
# .env.local（或 CI 的 env）
PJ52_FORUM_URL=https://www.52pojie.cn/forum-16-1.html   # 板块，默认精品软件区
PJ52_REPLY_TEXT=谢谢分享~                                # 回帖内容
PJ52_REPLY=0                                            # 置 0 = 只签到不回帖
PJ52_REPLY_STRICT=0                                     # 置 0 = 回帖失败不影响退出码
```

> ⚠️ **回帖是「跑一次发一条」**：同一天多跑几次就会多发几条。吾爱版规在发表回复按钮旁边
> 明写着「禁止复制他人回复等『恶意灌水』行为，违者重罚」—— 别把它当刷帖脚本用，
> 定时任务一天一条即可。

> **判定回帖成功的方式（踩了两个坑才定下来）**：Discuz 的响应是一段
> `succeedhandle_fastpost(...)` 脚本，**注入到 `<head>`**；而这套主题里没有定义
> 那个函数，所以**成功也不跳转、界面毫无变化**。同时 `#fastpostreturn` 里有个
> **隐藏的** `#fastpostreturn_wait`（内容恒为「请稍候...」），而 `textContent` 连隐藏
> 文本一起读 —— 只看它的话永远读到「请稍候...」。所以判定条件是扫脚本文本里的
> `succeedhandle_fastpost`（`read_reply_result()`），不看界面。

### 52pojie 还有一道 WAF（脚本已处理）

`home.php?mod=task`（签到任务页）被站点自家的 wzws WAF 保护，直接访问会跳到
`waf_text_verify.html` —— 一张 4 位小写字母的**图片验证码**。
脚本自动取图交给 ddddocr 识别后提交，识别错就换一张重来（换图不计入登录失败次数）。
所以**这一步必须真浏览器**，curl 拿到的一律是那个 5KB 的验证码页。

### 掘金：密码登录 + 滑块验证码（现状：位置对、拖动对，卡在行为风控）

点「登录」后弹的是**字节验证中心的滑块**，跑在 iframe 里：
`https://rmc.bytedance.com/verifycenter/captcha/v2?from=iframe&fp=verify_xxx`，
内部 `#captcha_verify_image`（背景，渲染 340×212 / 原始 552×344）、
`#captcha-verify_img_slide`（拼图块，68×68 / 110×110）、`.captcha-slider-btn`（拖动钮）。

**已经打通的**（2026-09-27 本机实测）：

| 环节 | 结果 |
|---|---|
| 缺口识别 | 直接用**元素截图**不行（那是合成画面，把拼图本身也拍进去了，会退化成"匹配到自己"）；要取 `src` 的**原始图片**，用带 alpha 掩码的 `TM_CCOEFF_NORMED`（拼图块是"亮版"、背景缺口是**压暗**过的，普通像素匹配会落到云/岩石上）。实测置信度 0.95~0.99，二维落点正落在缺口上 |
| 缩放换算 | 原始→渲染 = `渲染宽 / naturalWidth` = 340/552 = 0.6159 |
| 拖动 | 拼图块位移与计算距离**逐像素吻合**（例：算 221px，块从 x=20 → x=241） |
| 事件送达 | iframe 内 `pointerdown/move/up` 都能收到；ActionChains 每步会产生 pointer+mouse **成对**事件（看起来像 0ms 间隔，不是轨迹问题） |
| 轨迹控速 | 改用 CDP `Input.dispatchMouseEvent` + 显式时间戳，点间隔均匀 16~50ms、总时长 1.2~1.5s |
| ⚠️ 坐标坑 | Selenium 在 iframe 内给的是**iframe 局部坐标**，CDP 要**顶层视口坐标** → 得加上 iframe 的 rect 偏移（否则按下点打空、块纹丝不动） |

**没打通的**：服务端判定。轨迹过快/成对 0ms 时明确回
`{"code":502,"data":null,"message":"操作过快，请慢一点[5014]"}`
（接口 `POST //verify.zijieapi.com/captcha/verify?aid=2608&...&subtype=slide`）；
换成平滑拟人轨迹后变成**静默拒绝**（面板文案不变、`sessionid` 拿不到）。
字节这套是 ML 行为风控，合成事件难以稳定通过 —— 继续调参性价比很低。

所以脚本的策略是：**密码登录照跑（每轮换图重试），失败且配了 `JUEJIN_COOKIE` 就自动降级用 Cookie**，
保证签到这一步能落地。CI 上机房 IP 只会更难过风控，建议以 Cookie 为主。
取 Cookie 的办法与 52pojie 完全一样（Network → 刷新 → 点 Document 请求 →
Request Headers 里的 `cookie:` 整行，或右键 Copy as cURL）——掘金认 `sessionid`。



`home.php?mod=task`（签到任务页）被站点自家的 wzws WAF 保护，直接访问会跳到
`waf_text_verify.html` —— 一张 4 位小写字母的**图片验证码**。
脚本自动取图交给 ddddocr 识别后提交，识别错就换一张重来（换图不计入登录失败次数）。
所以**这一步必须真浏览器**，curl 拿到的一律是那个 5KB 的验证码页。

## 登录态与风控（重要）

聚宽有**自研的拼图滑块风控**，登录和签到都可能弹（触发时登录接口返回 `code=105`）。
所以本机运行做了两件事：

1. **固定浏览器 profile**：`Selenium/Check-in/.browser-profile/`。
   Chrome 用它启动，登录 cookie 留在里面，第二天跑的时候直接复用，**不用重新登录**。
   （该目录已在 `.gitignore` 里 —— 里面有你的登录 cookie，别提交。）
2. **首次运行需要你盯一下**：第一次跑会真的登录一次。如果弹出滑块验证码
   （`#yth_captchar`），手动拖过去即可 —— 那一次的登录态会被存下来。

想从头来过（比如怀疑 cookie 失效），删掉 profile 目录再跑：

```bat
rmdir /s /q "Selenium\Check-in\.browser-profile"
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
Selenium/Check-in/logs/joinquant-YYYY-MM-DD.log
```

跑完最后一行会给结论（是否检测到失败标记），失败时附上对应的原文。

## 踩过的坑（都已在代码里处理）

| 现象 | 原因 | 处理位置 |
|---|---|---|
| `WebDriverException: unhandled request` | 本机 shell 的 `http_proxy` 被 Selenium 套到了发往 chromedriver 的请求上 | `run_local.py` 启动子进程前清空代理变量 |
| 启动浏览器时进程直接 SIGTERM、日志只有一行 | Selenium Manager 要联网取 chromedriver，被本机安全策略杀掉 | 设 `CHECKIN_CHROMEDRIVER` 指一个现成 chromedriver.exe（`base.py` 的 Windows 分支） |
| `Invalid URL 'xxx'` | 飞书机器人 ID 像是 URL | 正常现象，用错 ID 才会出现 |
| 日志顺序错乱 | 子进程 stdout 走块缓冲，traceback 先冒出来 | 子进程加 `-u` |
| `pythonw` 下 `print` 直接抛异常 | 无控制台时 `sys.stdout` 是 `None` | 回退到 `os.devnull` |
| 每天弹一个浏览器窗口 | Windows 分支默认有头 | `.env.local` 里 `CHECKIN_HEADLESS=1` |
| 52pojie 签到页只有 5KB「请完成安全验证」 | 任务页被 wzws WAF 拦，需过图片验证码 | `52pojie.py` 的 `pass_waf()`，ddddocr 识别 |

## 搬到 Linux 服务器上跑（备选）

同样的脚本可以直接用，差异只有三处：

1. **cron 按本地时间排** —— 线上那个 `22 22 * * *` 是 UTC，等于北京 06:22；
   服务器上要写 `22 6 * * *`，直接抄数字会提前 8 小时。
2. **chromedriver 路径** —— `base.py` 的 Linux 分支硬编码 `/usr/bin/chromedriver`。
3. **系统依赖** —— `opencv-python` 需要 `libgl1` 和 `libglib2.0-0`。

```bash
22 6 * * * cd /path/to/GithubAction && /path/to/python -u Selenium/Check-in/run_local.py >> Selenium/Check-in/logs/cron.log 2>&1
```

## 线上怎么办

GitHub Actions 那边的聚宽步骤已经跑不通了（出口 IP 决定，改代码没用）。
建议从 `.github/workflows/check_in.yml` 里摘掉 `Check in JoinQuant` 这一步，
省得每天推一张假的失败卡片。其余站点（v2ex / fishpi / futu / weather）不受影响，原样留在 Actions 即可。
