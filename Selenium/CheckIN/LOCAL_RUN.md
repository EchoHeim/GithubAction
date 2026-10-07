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
Selenium\CheckIN\run_local.bat
```

或者直接调 Python：

```bash
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/CheckIN/run_local.py
```

## 跑其它站点（52pojie / 掘金）

`run_local.py` 支持用第一个参数选站点，不带参数就是聚宽（计划任务用的还是这条，没变）：

```bash
# 吾爱破解
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/CheckIN/run_local.py 52pojie

# 掘金
C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe -B Selenium/CheckIN/run_local.py juejin
```

各自的凭据在 `.env.local` 里填对应的一组：`PJ52_COOKIE`、
`JUEJIN_USERNAME/JUEJIN_PASSWORD`。
日志分别落 `logs/52pojie-YYYY-MM-DD.log`、`logs/juejin-YYYY-MM-DD.log`。

### 掘金：签到后会**自动进福利中心读矿石数 + 免费抽奖一次**（2026-09-29 加）

签到页只有「日历 + 立即签到」，**没有抽奖入口在右边**。真实入口是**左侧菜单的「幸运抽奖」**：

```
签到页 → 点左侧菜单「幸运抽奖」 → 转盘页 /user/center/lottery
       → 读顶部矿石胶囊（55174）→ 点「免费抽奖次数：N 次」→ 一同写进飞书卡片
```

卡片会多两行：

```
**当前矿石数**: 55174        ← 优先用抽奖页胶囊的值（是抽奖后的最新值）
**免费抽奖**: 已抽奖（免费 1 次）
**抽奖奖励**: 矿石 55174 → 55184   ← 只在矿石数有变化时出现
```

### 掘金：抽奖后**回首页 → 沸点广场 → 发一条沸点 + 给两名好友点赞**（2026-10-01 加）

流程（按 lodge 给的截图）：

```
签到 + 抽奖完成 → 回首页 → 点**导航栏的「沸点」** → 沸点广场 /pins
              → 顶部输入框写一句话 → 点「发布」
              → 在沸点列表里给 **2 名好友**点「点赞」
```

卡片会再多三行：

```
**发沸点**: 已发布沸点
**沸点内容**: 今天也要好好写代码呀~
**点赞**: 已点赞 2 名好友（喜马拉雅9527… / 科技热点…）
```

开关与相关环境变量：

```ini
JUEJIN_PINS=1                                        # 置 0 = 不做沸点（只签到 + 抽奖）
JUEJIN_PINS_TEXT=今天也要好好写代码呀~                 # 要发的内容
JUEJIN_PINS_LIKES=2                                  # 要点赞的好友数
JUEJIN_PINS_URL=https://juejin.cn/pins                # 沸点广场，默认值
```

> ⚠️ **这条流程跟签到/抽奖是三件独立的事**，任何一步失败都**不改签到结论、不动退出码**，
> 只写进卡片备注 —— 跟抽奖一个原则。`pins_activity()` 里那层宽口径 `except` 就是干这个的。

#### 沸点这条路的坑（都写进回归测试了）

| 坑 | 真因 | 修法 |
|---|---|---|
| **导航栏「沸点」点不到** | 线上掘金是构建过的 SPA，导航项**未必是 `<a href>`**（走 JS 路由），只认 `//a[@href='/pins']` 会全部落空 | 选择器按「href → 文案」分级，文案那条**不限定标签**（`a/li/div/span` 都收）；点不动才降级为直接开 `/pins` |
| **点错「发布」按钮** | 页面上「发布沸点」标题、左侧「发布」入口都含「发布」二字，全页模糊匹配必中错的那个（跟抽奖按钮那次一模一样） | 从发布框**往上爬 6 层**，在所在容器内找文案恰为「发布/发布沸点/立即发布」的按钮；容器内没有才退到全局 |
| **`contenteditable` 喂字丢字符** | 发布框可能不是 `textarea` 而是可编辑 div，直接 `send_keys` 会丢 | 按 `tagName` 分流：`textarea` 走 `send_keys`，可编辑 div 走 `execCommand('insertText')` |
| **判「发布成功」扫整页文案** | 会吃到旁边别人的内容/系统播报（跟抽奖那条教训同源） | 只用**结构性判据**：发布框是否已清空。清空 = 提交走了 |
| **见谁都点赞** | lodge 明确要「**两名好友**」 | 卡片里出现独立「关注」按钮 = 这人未关注（不是好友）→ 跳过；「已赞/取消赞」→ 跳过不重复点 |
| **点到右侧「精选沸点」栏** | 右侧推荐栏也有「点赞」按钮 | 按**卡片结构**框选（宽度 > 400px 且不含「精选沸点」字样），并剔除祖先含「精选沸点」的按钮 |
| **把「31赞」当点赞按钮** | 卡片计数文案也含「赞」字 | 只认文案**恰为**「点赞」的元素 |
| **筛不满 2 名好友** | 可能当天好友都没发沸点 | 切**宽松模式**补足（仍避开已赞、仍不碰精选栏），不让这一步白跑；日志里说明是宽松模式点的 |

### ⚠️⚠️ 2026-09-29 线上连跑三轮全错，坑逐一记录（**别再走回头路**）

> ⚠️ **第 5 轮（2026-09-29）按 lodge 要求砍掉了「抽奖结果确认」**。
> 原话：「现在抽奖可以正常，实际就是没有抽奖反馈。**不用获取抽奖确认**。」
> 所以 `lottery_free_draw` 现在是**点完即返回**：不再等 25 秒、不再判成功。
> 之前那套「免费次数变小 / 按钮转已抽完 / 矿石变化 / 弹层奖品」四重判据在他那边
> 全落空、判成「抽奖未确认」，而实际抽奖是成功的 —— **等待与确认纯属多余复杂度**。
> 连带删掉：`_read_reward_from_modal` / `_close_lottery_modal` / `LOTTERY_CLOSE_XPATHS`。

开关与相关环境变量：

```ini
JUEJIN_LOTTERY=0                                          # 置 0 = 只签到不抽奖
JUEJIN_LOTTERY_URL=https://juejin.cn/user/center/lottery   # 抽奖页，默认值
```

### 掘金：抽奖后**沸点跑两遍 + 文章详情页点赞收藏关注**（2026-10-01 加，当日第二轮）

流程（按 lodge 给的截图）：

```
签到 + 抽奖完成
  → 【沸点】回首页 → 点导航栏「沸点」→ 沸点广场 /pins
           → 顶部输入框写一句话 → 点「发布」
           → 给 2 名好友点「点赞」
  → 等 120 秒，**再跑一遍**（第 2 轮文案加后缀「（2）」，避免与第一轮重复）
  → 【文章】回首页 → 点**第 1 篇文章**（⚠️ **在新标签页打开**）→ 文章详情页
           → 左侧操作栏点「赞」→ 点「收藏」→ 弹窗选**默认收藏夹** → 点「确定」
           → 右侧作者信息下方**有关注按钮就点**，已关注则忽略
  → 关掉文章标签回首页，点**第 2 篇**，把上面这套**重复一遍**
```

卡片会再多三行：

```
**发沸点**: 已发布沸点 ×2                             ← 两轮同样结果折叠成 ×2
**沸点内容**: 今天也要好好写代码呀~ / 今天也要好好写代码呀~（2）
**点赞**: 已点赞 2 名好友 ×2（喜马拉雅9527… / 科技热点…）
**文章点赞**: 已点赞文章 ×2
**文章收藏**: 已收藏文章 ×2
**关注作者**: 已关注作者 ×2
```

开关与相关环境变量：

```ini
JUEJIN_PINS_ROUNDS=2     # 沸点跑几遍，默认 2
JUEJIN_PINS_GAP=120      # 两遍之间间隔秒数，默认 120
JUEJIN_ARTICLE=0         # 置 0 = 不做文章详情页（点赞/收藏/关注）
JUEJIN_ARTICLE_COUNT=2   # 文章做几篇，默认 2（做完一篇回首页点下一篇）
```

> ⚠️ 现在整条链是「签到 → 抽奖 → 沸点×2 → 文章详情页」，**每一步都是独立的事**，
> 前面成了后面挂了不影响签到结论、不动退出码（各自内部都有宽口径 `except`）。
>
> ⚠️ **发沸点是「跑一次发一条」** —— 现在一轮跑 2 条，一天手动多跑几次就会多刷。
> 定时任务一天一次（2 条）尚可；要更保守就把 `JUEJIN_PINS_ROUNDS` 设回 1。

#### 沸点两遍 + 文章详情页这一轮的坑（都写进回归测试了）

| 坑 | 真因 | 修法 |
|---|---|---|
| **⚠️⚠️ 文章是「新标签页」打开的** | 首页文章链接带 `target=_blank`（掘金默认如此）。点完**当前 driver 仍停在首页句柄上** —— 不切句柄就去点左侧赞，等于在首页上瞎找，必报「找不到按钮」。而且不关旧标签，句柄越攒越多，第二篇就点不动了 | 点击**前**记下句柄集合 → 点击 → 轮询等**新句柄**出现 → `switch_to.window` 过去；做完 `_close_article_tab()` 关掉文章标签并切回首页。拿不到新句柄才退回「直接开 href」兜底 |
| **第二篇要点另一篇** | lodge 要求「返回首页，重复点击另一篇文章，重复一次」 | `_article_xpaths(idx)` 把 XPath 里的 `[%d]` 换成第 N 篇；`article_activity` 循环 `ARTICLE_COUNT` 篇，每篇都重新回首页点链接 |
| **两轮沸点内容一字不差** | 短时间发完全相同的重复内容，观感像刷屏，站点也可能拦 | 第 2 轮起文案加轮次后缀「（N）」（`_round_text`），语义不变但可辨识 |
| **文章左侧「赞 / 收藏」定位不到** | 那排按钮**只有图标 + 数字，没有「点赞」二字**，靠文案必落空 | 「收藏」按类名找（class 带 `collect`）；「赞」见下面两条 |
| **⚠️ 点赞按钮线上根本没有 `like` 类名**（2026-10-02 lodge 实测） | 类名法在真实站点**一条都命中不了**，两篇文章全报「未找到点赞按钮」；而同一列的「收藏」class 带 `collect`，稳定命中 | 拿收藏当锚点**反推同列第 1 个按钮** —— 该列顺序固定（赞/评论/收藏/分享/举报，lodge 截图确认）：从收藏往上爬到「同列容器」那一层（判据：≥3 个、尺寸相近、竖向排开），取收藏**前面第 2 个** |
| **反推出的按钮不知道是否已赞，一点就成「取消赞」** | 掘金点赞是 toggle，已赞再点计数 -1 | 点完**复核计数**：`+1` 算成功；`-1` 说明误取消 → **立即补点还原**；`0` 当已赞跳过。回归测试 T24b 专守这条 |
| **⚠️ 夹具把点赞按钮写成 `like-btn`，测试「假过」** | 夹具 class 带 like，32 条断言全绿，线上却一个按钮都找不到 —— 夹具比真实站点「友好」等于没测 | 夹具照实还原：点赞按钮**不给 like 类名**，并补上真实 48×48 竖排尺寸；点赞也改成 toggle（照实模拟「再点会取消」） |
| **收藏点「确定」点到了无关按钮** | ① 弹窗根取成了**整屏遮罩**，把被遮住的无关「确定」也圈进来了；② **Selenium 大坑**：`element.find_elements(By.XPATH, "//button")` **不是**在子树里找，绝对路径 `//` 会忽略调用它的元素，退化成全文档查找 | ① 浮层取**最小**的那个（弹窗内容本体），不是最大的遮罩；② 新增 `_scope_xpath()`，把 `//` 转成 `.//` 才真正限定子树（症状是点报 `element click intercepted`） |
| **弹窗判据用尺寸阈值** | 真实弹窗有固定宽高，但精简 DOM 会很矮，`height>=150` 把真弹窗毙了 | 改成「文案 + 浮层形态」双判：`position:fixed/absolute` 或类名含 `modal/dialog/popup/mask` |
| **「关注」点错地方** | 页头导航也有「关注」标签，全页模糊匹配会点错 | 限定在**作者卡片**内：用「私信」按钮当锚点找同区域的「关注」 |
| **已关注又点一次** | 重复执行会把「已关注」点成**取消关注** | 先读作者卡文案，命中「已关注/互相关注」直接跳过 |
| **左侧按钮宽度被误判** | 操作项容器被 flex 拉满整行（实测宽 700+），用宽度上限过滤会把真按钮整条毙掉 | 只卡**高度**上限（>80 排除整块），再 `_innermost_match` 钻到最内层可点元素 |
| **本机跑报 `unhandled request`**（session 建得起、之后每步全挂） | 本机挂着 `HTTP_PROXY` 却没设 `NO_PROXY`（代理软件常这样），Selenium 连**本机 chromedriver** 的 HTTP 请求也被代理接管，代理不认识 `/session/<id>/execute/sync` 这种路径。**看着像元素定位问题，其实是环境问题** | `Selenium/base.py` 新增 `_bypass_proxy_for_localhost()`，建 driver 前把 `localhost/127.0.0.1/::1` 追加进 `NO_PROXY`（只追加、不覆盖）；回归测试同样调用它 |

### ⚠️⚠️ 2026-09-29 线上连跑三轮全错，坑逐一记录（**别再走回头路**）

三轮的共同点：**逻辑看起来对、跑真站点全错**。所以都写进回归测试了。

| 现象 | 真因 | 修法 |
|---|---|---|
| **进错页面，压根没有转盘** | 第 1 轮走「头像菜单 → 成长福利」→ `/user/center/growth`，那页是**「成长等级」**（掘友分/等级权益/去上传）。第 2 轮 lodge 截图指正：入口是**签到页左侧菜单的「幸运抽奖」**，跳 `/user/center/lottery` | 改为「签到页 → 左侧菜单『幸运抽奖』→ 转盘页」，头像菜单只留作最后兜底 |
| **URL 对了但页面错了仍判成功** | 第 1 轮只看 URL 命中 `/growth` 就认为进对了 | 判据换成**页面内容双向校验**：有「幸运大转盘/免费抽奖次数」且**没有**「掘友分明细/等级规则/等级权益」→ `_on_lottery_page()` |
| **矿石数读成 25000** | 那是成长等级页「JY8 **25000**」的等级阈值！扫纯数字时没排除等级/分值语义 | JS 取值加 EXCLUDE 词表（等级/JY/掘友分/还需/次数…），并优先「邻近有『矿石』字样」的候选 |
| **签到页读数串位** `矿石=2026 累计=50174` | 三个统计卡是**数字在上、标签在下**（`55174` 在 `当前矿石数` 上面）。用「标签后跟数字」的文本正则去配，必然吃到**下一个卡片**的数字 | 改走 **DOM 结构**：找标签元素 → 取同卡片内数字（`SIGNIN_STATS_JS`）；文本正则只作兜底且改成「数字在前」。**第 3 轮 CI 已验：矿石=55174 连续=4 累计=5** ✅ |
| 点到了**左侧导航菜单项** | 「幸运抽奖」也含「抽奖」二字，模糊匹配必中；且线上菜单项外层全是构建哈希类名，`not(@class='nav')` 挡不住 | **放弃「抽奖」模糊匹配**，改认 `免费抽奖次数` 独有文案 + 结构校验 + 菜单文案黑名单 |
| **矿石数又读成 2026**（第 5 轮） | ① 抽奖页胶囊**邻近没有「矿石」二字**——只是「🔶 图标 + 数字」，所以「邻近有矿石字样」的策略全落空；② 落空后掉到整页兜底正则 `矿石(\d+)`，抓到的是页面别处的 **`© 2026 稀土掘金` 的年份** | ① 主路径改成「**页面最上方的大数字**」（胶囊必在 banner 顶部）；② 新增 `_looks_like_year()` 排除 1900~2099 四位年份；③ 兜底正则收紧为 `矿石[^\d]{0,6}(\d[\d,]{2,})` 且逐个过滤年份 |

**还修了一个隐蔽坑**：`driver.execute_script` 默认**同步**语义，我一开始写成
`arguments[arguments.length-1]` 回调式（异步），报 `cb is not a function`，
矿石数/免费次数全读不到。已全部改 `return`。

**判成功的判据（历史，第 5 轮已整体取消）**：曾是「① 免费次数 N→N-1 ② 按钮转已抽完
③ 矿石数变化 ④ 中奖弹层里出现奖品」四条。**现已全部删除** —— 点完即返回。

⚠️ 但第 4 条留下的教训必须记住：**别扫整页文案找「恭喜/抽中」** —— 页面右侧「围观大奖」栏
一直在播报**别人**的中奖（`恭喜 胡毛毛 抽中 Pico Neo3`），扫整页必然把「一下没抽」报成
「抽奖成功」（第 1 轮就死在这）。**任何"中奖"判据都不许扫整页文案**，只能是结构性的。

**矿石数「顶部杂数字抢答」这个洞**：第 5 轮暴露后，除 `_looks_like_year()` 外又加固了
`ORES_INLINE_JS` —— EXCLUDE 词表补 `消息/通知/角标`，并对 **y < 80 且类名含
`badge|red-dot|count|unread`** 的数字直接判死。回归测试的 T4 专门放了 4 位数页头角标
（`消息 1234` / `未读 5678`）来守它。

**回归测试**：`Selenium/CheckIN/juejin_regress_test.py`（合成 DOM，还原上述全部陷阱，
**33 项断言**，含沸点流程 T11~T22、文章详情页 T23~T31 与 T24b）。改动选择器后**务必重跑**：

```bash
python -B Selenium/CheckIN/juejin_regress_test.py
# 代理问题已在脚本内自动绕开；万一仍报 unhandled request，手工兜底：
# env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
#   python -B Selenium/CheckIN/juejin_regress_test.py
```


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

### 回帖（默认开）+ 卡片里的积分与吾爱币

签到之后脚本会去『**精品软件区**』（fid=16）**随机挑 2 个互不相同的普通帖**
（跳过置顶/公告），逐个在快捷回复框里发一条 `谢谢分享~`，**两条之间等 20 秒**，
并把**当前积分**（页头 `#extcreditmenu`）、**吾爱币**（设置 → 积分页）和
每个帖的回帖结果一起写进飞书卡片。相关开关：

```ini
# .env.local（或 CI 的 env）
PJ52_FORUM_URL=https://www.52pojie.cn/forum-16-1.html   # 板块，默认精品软件区
PJ52_REPLY_TEXT=谢谢分享~                                # 回帖内容
PJ52_REPLY_COUNT=2                                       # 回几个帖子
PJ52_REPLY_INTERVAL=20                                   # 两条之间隔几秒
PJ52_REPLY=0                                            # 置 0 = 只签到不回帖
PJ52_REPLY_STRICT=0                                     # 置 0 = 回帖失败不影响退出码
PJ52_CREDIT_URL=https://www.52pojie.cn/home.php?mod=spacecp&ac=credit  # 吾爱币页，默认值
```

卡片长这样：

```
**签到状态**: 签到成功
**当前积分**: 57                    ← 页头那个「积分」，是**总积分**
**吾爱币**: 413 CB                  ← 设置 → 积分页的吾爱币
**回帖**: 2/2 成功｜xxx → 回帖成功（pid=…）｜yyy → 回帖成功（pid=…）
**时间**: 2026-09-29 12:49:33
```

> ⚠️ **页头的「积分: 57」不是吾爱币，两者别混**（2026-09-29 lodge 指出）。
> 页头那个是**总积分** = 发帖数×0.1 + 热心值×1.2 + 悬赏值×1.5 + 贡献值×1.5
> + 威望×20 + 精华帖数×100 − 违规×20（积分页上明写了这条公式），
> 而吾爱币是另一种货币。所以吾爱币必须**单独打开 `home.php?mod=spacecp&ac=credit` 读**。

> ⚠️ **两项都在回帖之后读**（2026-09-29 改）。回帖本身 +1 吾爱币，
> 原来「签到后立刻读积分、再回帖」的顺序读到的是**回帖前**的旧值；
> 现在统一挪到回帖完成后读一次，卡片上就是最终值。

吾爱币抽取逻辑有离线回归测试（合成 DOM，**不需要登录态**），改了 `CREDIT_EXTRACT_JS`
或相关选择器就重跑：

```bash
python -B Selenium/CheckIN/52pojie_credit_test.py            # 含合成 DOM（要 Chrome）
python -B Selenium/CheckIN/52pojie_credit_test.py --offline  # 只跑纯逻辑
```

用例覆盖：截图里的真实结构（`dt` 标签 + `dd > em` 数字）、`credit_num` 老模板、
内联文本、千分位、以及两个陷阱 —— **吾爱币排在贡献值/热心值之后**、
**旁边晃着一个「积分: 57」**。

> ⚠️ **两条之间必须等20 秒，这是硬要求不是礼节**（Discuz 对连续发表有
> 「两次发表间隔少于 15 秒」的限制，间隔不够第二条会被直接拒，回执是
> 「抱歉，您的两次发表间隔少于 15 秒」）。`PJ52_REPLY_INTERVAL` 默认 20 秒，
> 别往 15 以下调。

> ⚠️ **两个帖子必须互不相同**（2026-10-07 lodge 要求）。脚本按 tid 去重后
> `random.sample` 抽样；**候选不够就报错，不会拿同一个帖凑数** —— 对同一个帖
> 回两次 Discuz 会拦（重复回复），更糟的是这就成了刷帖。
> 默认板块 fid=16 是实测来的：fid=5 是脱壳破解区、fid=6 是动画发布区，
> 12/14/33 根本不存在（访问会落到「提示信息」页）。

> ⚠️ **回帖是「跑一次发两条」**：同一天多跑几次就会多发。吾爱版规在发表回复按钮旁边
> 明写着「禁止复制他人回复等『恶意灌水』行为，违者重罚」—— 别把它当刷帖脚本用，
> 定时任务一天一次即可。

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

1. **固定浏览器 profile**：`Selenium/CheckIN/.browser-profile/`。
   Chrome 用它启动，登录 cookie 留在里面，第二天跑的时候直接复用，**不用重新登录**。
   （该目录已在 `.gitignore` 里 —— 里面有你的登录 cookie，别提交。）
2. **首次运行需要你盯一下**：第一次跑会真的登录一次。如果弹出滑块验证码
   （`#yth_captchar`），手动拖过去即可 —— 那一次的登录态会被存下来。

想从头来过（比如怀疑 cookie 失效），删掉 profile 目录再跑：

```bat
rmdir /s /q "Selenium\CheckIN\.browser-profile"
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
Selenium/CheckIN/logs/joinquant-YYYY-MM-DD.log
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
22 6 * * * cd /path/to/GithubAction && /path/to/python -u Selenium/CheckIN/run_local.py >> Selenium/CheckIN/logs/cron.log 2>&1
```

## 线上怎么办

GitHub Actions 那边的聚宽步骤已经跑不通了（出口 IP 决定，改代码没用）。
建议从 `.github/workflows/check_in.yml` 里摘掉 `Check in JoinQuant` 这一步，
省得每天推一张假的失败卡片。其余站点（v2ex / fishpi / futu / weather）不受影响，原样留在 Actions 即可。
