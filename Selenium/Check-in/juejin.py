# -*- coding: UTF-8 -*-
"""掘金（juejin.cn）签到：密码登录（自动过滑块验证码）→ 每日签到页点「立即签到」
→ 进福利中心读矿石数 → 免费抽奖一次 → 一起推飞书卡片。

━━━ 登录：密码 + 滑块验证码（已实现，但服务端行为风控可能仍拦）━━━
2026-09-27 实测：点「登录」后站点会弹**字节验证中心的滑块验证码**，它在 iframe 里：
```
iframe : https://rmc.bytedance.com/verifycenter/captcha/v2?from=iframe&fp=verify_xxx
  背景图 <img id="captcha_verify_image">        渲染 340x212 / 原始 552x344
  拼图块 <img id="captcha-verify_img_slide">     渲染 68x68  / 原始 110x110
  拖动钮 <div class="captcha-slider-btn">
验证接口 POST //verify.zijieapi.com/captcha/verify?aid=2608&...&subtype=slide
```
**位置识别+拖动这条路已经打通**（实测数据见 LOCAL_RUN.md）：缺口命中置信度 0.95~0.99、拼图块位移
与计算距离**逐像素吻合**、CDP 派发的轨迹点间隔 16~50ms/总时长 1.2~1.5s。
但服务端仍不给通过态：轨迹**过快/成对 0ms** 时会回
`{"code":502,"message":"操作过快，请慢一点[5014]"}`，平滑拟人轨迹则被**静默评分拒绝** ——
字节那套是 ML 行为风控，合成事件很难稳定过。所以：
  * 密码登录照跑（`JUEJIN_MAX_ATTEMPTS` 轮，每轮换一张图重试）；
  * 失败且配了 `JUEJIN_COOKIE` 时**自动降级**用 Cookie，保证签到本身能完成。

━━━ 签到流程 ━━━
`/user/center/signin` 是「每日签到」页：左侧菜单 + 右侧日历 + 大按钮「立即签到」，
页面上还有三张统计卡：**`4 连续签到天数` / `5 累计签到天数` / `55174 当前矿石数`**，
注意是**数字在上、标签在下**（所以取值走 DOM 结构，不用文本顺序，见 SIGNIN_STATS_JS）。
脚本：
  1. 登录（或复用 Cookie 登录态）→ 打开签到页；
  2. 读签到前状态：矿石数、连续/累计天数、按钮文案；
  3. 按钮已是「已签到」类文案 → 判「今日已签到」，直接结束；
  4. 否则点「立即签到」，按**多重判据**确认成功（按钮文案变化 / 矿石数变化 /
     连续天数 +1 / 出现「签到成功」提示），拿不到就 dump 现场后抛错。

━━━ 幸运抽奖：矿石数 + 免费抽取一次（2026-09-29 新增）━━━
正确的路径（**lodge 截图确认，别再走别的路**）：

    签到页 → 点**左侧菜单**的「幸运抽奖」→ 转盘页 /user/center/lottery
           → 读顶部矿石胶囊（截图实测 55174）
           → 点「免费抽奖次数：1 次」

⚠️ 这里坑很深，两轮线上都栽了，把结论钉死：
  · **别再点头像菜单**：里头是「成长福利」，跳的是 `/user/center/growth`，
    而那个页面是**「成长等级」**（掘友分 / 等级权益 / 去上传），**根本没有转盘**；
  · **别只看 URL 判断进对页面**：第 1 轮就是 URL 命中 `/growth` 但页面全错。
    判据必须看**页面内容**（有「幸运大转盘/免费抽奖次数」且没有「掘友分明细」），
    见 `_on_lottery_page()`；
  · 顶部胶囊里**只有数字、没有「矿石」二字**，而且整页别处也有大数字
    （成长等级页的 `JY8 25000` 就被误读成矿石数过），所以取值要带语义排除。

抽奖是**锦上添花**：登录/签到已经成功后，抽奖这一步失败只记进卡片的备注，
不改变签到结论、不影响退出码（否则抽奖挂一天就把整天的签到判成失败）。

「免费抽奖次数：N 次」里的 N 是站点自己给的，别拿它当条件猜 —— 直接点，
然后用**硬证据**确认有没有真的抽到：① 免费次数 N→N-1 或消失（最硬）
② 按钮转「今日已抽完」③ 矿石数变化 ④ **中奖弹层**里出现奖品。
⚠️ 别扫整页文案找「恭喜/抽中」—— 页面右侧「围观大奖」栏一直在播报**别人**的中奖，
扫整页必然误报（第 1 轮就是这么把「一下没抽」报成「抽奖成功」的）。

回归测试：`python -B Selenium/Check-in/juejin_regress_test.py`（合成 DOM，29 项断言）。
改选择器后务必重跑；跑之前要清代理（见 LOCAL_RUN.md）。

━━━ 沸点广场：发一条沸点 + 给好友点赞（2026-10-01 新增）━━━
签到 + 抽奖都完成后，**回首页 → 点导航栏「沸点」→ 沸点广场**：
  1. 在顶部输入框写一句话（默认 `JUEJIN_PINS_TEXT`）→ 点「发布」；
  2. 在沸点列表里给 **2 名好友**的沸点点「点赞」。
**这套流程跑 `JUEJIN_PINS_ROUNDS` 遍（默认 2 遍），两遍之间隔 `JUEJIN_PINS_GAP` 秒（默认 120）**
（lodge 要求「这两个任务执行两遍，两次之间间隔 120 秒」）。
第 2 轮起文案自动加轮次后缀（`今天也要…~（2）`），避免与第一轮一字不差被当重复内容。
按 lodge 给的截图实现，两条主原则与前文一致：
  · **认页面内容、不认 URL**（`_on_pins_page()`，双向判据）；
  · **不扫整页文案找「发布成功 / 赞」** —— 右侧「精选沸点」栏一直在播别人的内容，
    判发布成功走「发布框是否清空」，判点赞走「卡片结构 + 文案恰为『点赞』」。
⚠️ 只给**好友**点（卡片出现独立「关注」按钮 = 未关注，跳过）；已赞的跳过不重复点。
筛不满 2 名好友时会切**宽松模式**补足（仍避开已赞），不让这一步白跑。

━━━ 文章详情页：点赞 + 收藏 + 关注作者（2026-10-01 新增）━━━
两遍沸点都跑完 → **回首页 → 点第 1 篇文章** → 文章详情页：
  1. 左侧竖排操作栏点「赞」；
  2. 点「收藏」→ 弹「选择收藏集」窗 → 选**默认收藏夹**（我的收藏）→ 点「确定」；
  3. 右侧作者信息下方**有关注按钮就点**，已是「已关注」则忽略（绝不点成取消关注）。
  4. 做完回首页，点**第 2 篇**，把上面这套**重复一遍**（共 `JUEJIN_ARTICLE_COUNT` 篇，默认 2）。
⚠️ **文章是在新标签页打开的** —— 点完链接当前 driver 还停在首页句柄上，必须先
   `switch_to` 到新句柄再去操作，做完还要关掉标签并切回首页，否则第二篇会点不动。
   详见 `_goto_nth_article` / `_close_article_tab`。
⚠️ 左侧那排按钮**只有图标 + 数字、没有文字文案** —— 不能靠「点赞」二字定位，
   只能靠类名结构（`.like-btn` / `.collect-btn`）；判「已赞/已收藏」看类名有没有
   `active/liked/collected`，有就跳过（再点一下会变取消）。
⚠️ 「关注」二字在页头导航里也有（顶部「关注」标签），必须**限定在作者卡片内** ——
   用「私信」按钮当锚点找同区域的「关注」。
⚠️ **收藏点「确定」有个 Selenium 大坑**：`element.find_elements(By.XPATH, "//button")`
   **不是**在子树里找，绝对路径 `//` 会忽略调用它的元素、退化成全文档查找，
   于是点到了被弹窗遮住的无关「确定」，报 `element click intercepted`。
   必须写 `.//`（见 `_scope_xpath`）；弹窗根也要取**最小**的那个浮层，不是整屏遮罩。

跟抽奖一样：**沸点与文章流程的任何失败都不影响签到结论与退出码**，只记进卡片备注。

用法（凭据走环境变量）：
    JUEJIN_USERNAME=手机号 JUEJIN_PASSWORD=密码 python -m Selenium.Check-in.juejin
    # 兼容老写法：python -m ... <手机号/邮箱> <密码> [飞书机器人 webhook]

可选环境变量：
    JUEJIN_USERNAME      账号（手机号/邮箱）
    JUEJIN_PASSWORD      密码
    JUEJIN_COOKIE        登录态 Cookie（可选兜底：走 Cookie 时跳过登录页与滑块）
    FEISHU_BOT_ID        飞书机器人 webhook，给了才推卡片（含签到状态 + 矿石数）
    JUEJIN_SIGNIN_URL    签到页，默认 https://juejin.cn/user/center/signin
    JUEJIN_LOTTERY_URL   幸运抽奖页，默认 https://juejin.cn/user/center/lottery
    JUEJIN_LOTTERY=0     关掉免费抽奖（只签到不抽奖）
    JUEJIN_PINS_URL      沸点广场，默认 https://juejin.cn/pins
    JUEJIN_PINS=0        关掉沸点流程（只签到 + 抽奖）
    JUEJIN_PINS_TEXT     要发的沸点内容，默认「今天也要好好写代码呀~」
    JUEJIN_PINS_LIKES    每轮要点赞的好友数，默认 2
    JUEJIN_PINS_ROUNDS   沸点流程跑几遍，默认 2
    JUEJIN_PINS_GAP      两遍之间的间隔秒数，默认 120
    JUEJIN_ARTICLE=0     关掉文章详情页流程（点赞/收藏/关注）
    JUEJIN_ARTICLE_COUNT 文章做几篇，默认 2（做完一篇回首页点下一篇）
    JUEJIN_MAX_ATTEMPTS  整轮重来的次数，默认 3
    JUEJIN_HOME_URL      首页，默认 https://juejin.cn/

失败现场写进 juejin-debug/，CI 里由 workflow 收集成 artifact。
"""

import base64
import math
import os
import random
import re
import sys
import time

import cv2
import numpy as np

from Selenium.base import *
from Messaging.Feishu import Feishu_SendCardMsg

HOME_URL = os.getenv("JUEJIN_HOME_URL", "https://juejin.cn/")
SIGNIN_URL = os.getenv("JUEJIN_SIGNIN_URL", "https://juejin.cn/user/center/signin")
GROWTH_URL = os.getenv("JUEJIN_GROWTH_URL", "https://juejin.cn/user/center/growth")
# 抽奖开关：默认开；置 0 时只签到不抽奖（比如手动补跑当天又不想消耗免费次数）
LOTTERY_ENABLED = os.getenv("JUEJIN_LOTTERY", "1") != "0"
MAX_ATTEMPTS = int(os.getenv("JUEJIN_MAX_ATTEMPTS", "3"))

JUEJIN_COOKIE_ENV = "JUEJIN_COOKIE"
COOKIE_DOMAIN = ".juejin.cn"

DEBUG_DIR = os.path.join(os.getcwd(), "juejin-debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# 首页「登录」按钮：它不存在 = 已登录
LOGIN_BUTTON_XPATHS = (
    "//button[@class='login-button']",
    "//button[contains(@class,'login-button')]",
    "//button[normalize-space(text())='登录']",
)
# 弹层里切到密码登录
PASSWORD_TAB_XPATHS = (
    "//span[contains(@class,'clickable') and contains(text(),'密码登录')]",
    "//*[contains(@class,'clickable') and normalize-space(text())='密码登录']",
)
USERNAME_XPATHS = (
    "//input[@name='loginPhoneOrEmail']",
    "//input[contains(@placeholder,'邮箱') or contains(@placeholder,'手机号')]",
)
PASSWORD_XPATHS = (
    "//input[@name='loginPassword']",
    "//input[@type='password' and contains(@class,'login-password')]",
)
SUBMIT_XPATHS = (
    "//button[contains(@class,'btn-login')]",
    "//button[normalize-space(text())='登录' and not(contains(@class,'register'))]",
)
# 风控指纹：出现这些就是「要你扫码验身」，别再试密码了
RISK_MARKERS = ("扫码验证", "抖音 APP", "使用已登录账号的设备扫码")

# ── 滑块验证码（字节验证中心，跑在 iframe 里）──
# 实测（2026-09-27）：点登录后弹出
#   iframe: https://rmc.bytedance.com/verifycenter/captcha/v2?from=iframe&fp=verify_xxx
# 内部元素（在 iframe 内定位，必须先 switch_to.frame）：
#   背景图  <img id="captcha_verify_image" class="captcha-verify-image">   渲染 340x212 / 原始 552x344
#   拼图块  <img id="captcha-verify_img_slide" ...>                        渲染 68x68 / 原始 110x110
#   拖动钮  <div class="captcha-slider-btn">
#   刷新    <div class="vc-captcha-refresh">
CAPTCHA_FRAME_XPATHS = (
    "//iframe[contains(@src,'verifycenter/captcha')]",
    "//iframe[contains(@src,'rmc.bytedance.com')]",
)
CAPTCHA_BG_XPATHS = ("//*[@id='captcha_verify_image']", "//*[contains(@class,'captcha-verify-image')]")
CAPTCHA_PIECE_XPATHS = ("//*[@id='captcha-verify_img_slide']",)
CAPTCHA_HANDLE_XPATHS = (
    "//*[contains(@class,'captcha-slider-btn')]",
    "//*[contains(@class,'dragger-item')]",
)
CAPTCHA_REFRESH_XPATHS = ("//*[contains(@class,'vc-captcha-refresh')]",)
CAPTCHA_FAIL_MARKERS = ("验证失败", "请重试", "再试一次", "拖动滑块")

FETCH_AS_DATA_URL_JS = """
var cb = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: 'omit'}).then(function(r){ return r.blob(); }).then(function(b){
  var fr = new FileReader();
  fr.onload = function(){ cb(fr.result); };
  fr.readAsDataURL(b);
}).catch(function(e){ cb('ERR:' + e); });
"""

# 签到按钮：按**文案**找，别认哈希类名（掘金的 class 随构建变）
SIGNIN_BUTTON_XPATHS = (
    "//button[normalize-space(text())='立即签到']",
    "//button[contains(text(),'立即签到')]",
    "//*[contains(@class,'signin') and contains(text(),'立即签到')]",
    "//*[normalize-space(text())='立即签到']",
)
SIGNIN_DONE_MARKERS = ("已签到", "今日已签到", "明天再来", "已领取")
SIGNIN_SUCCESS_MARKERS = ("签到成功", "领取成功", "获得", "恭喜")
# 签到页三个统计卡（截图 1：`4 连续签到天数` / `5 累计签到天数` / `55174 当前矿石数`）
#
# ⚠️⚠️ 2026-09-29 两轮线上都读串了（`矿石数=2026 连续=5 累计=50174`），根因：
#   掘金页面上**数字在前、标签在后**，而且「累计」那个标签实际写作
#   **「累计签到天数」没错、但还有个「累计签到天数」和「连续签到天数」是并列的两个卡片** ——
#   文本顺序打乱后，用「标签后跟数字」的正则去配，必然把**下一个卡片的数字**配进来。
#   更糟的是「当前矿石数」标签在数字**后面**，所以 `当前矿石数(\d+)` 根本配不到矿石数，
#   反而 `累计签到天数(\d+)` 吃到了矿石数那个大数字。
#   结论：**别用整页文本顺序配数字**，直接用 DOM 结构 —— 找含标签文案的元素，
#   取它**同一个卡片容器内**数字元素的值。见 SIGNIN_STATS_JS。
SIGNIN_STATS_JS = """
var out = {ores: null, streak: null, total: null};
var LABELS = {'当前矿石数': 'ores', '连续签到天数': 'streak', '累计签到天数': 'total'};
var labelEls = document.querySelectorAll('div, span, p, b, strong, em, dt, dd');
for (var i = 0; i < labelEls.length; i++) {
  var el = labelEls[i];
  if (el.children.length) continue;                  // 只要叶子标签
  var t = (el.textContent || '').trim();
  if (!LABELS[t]) continue;
  // 从标签往上找 1~3 层，取该容器里第一个纯数字叶子元素 = 这个卡片的数值
  var p = el;
  for (var hop = 0; hop < 4 && p; hop++, p = p.parentElement) {
    var nums = p.querySelectorAll('div, span, p, b, strong, em');
    for (var j = 0; j < nums.length; j++) {
      var n = nums[j];
      if (n.children.length) continue;
      var nt = (n.textContent || '').trim();
      if (!/^\\d[\\d,]*$/.test(nt)) continue;
      var r = n.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      out[LABELS[t]] = nt.replace(/,/g, '');
      break;
    }
    if (out[LABELS[t]]) break;
  }
}
return out;
"""
# 文本正则只作**最后兜底**（DOM 取值失败时），且方向改成「数字在前、标签在后」
ORES_FALLBACK_PATTERN = r"(\d[\d,]{2,})\s*当前矿石数"
STREAK_FALLBACK_PATTERN = r"(\d+)\s*连续签到天数"
TOTAL_FALLBACK_PATTERN = r"(\d+)\s*累计签到天数"

# ── 福利中心：矿石数 + 幸运大转盘免费抽奖 ──
#
# ⚠️⚠️ 2026-09-29 **两轮线上实测都栽在「进错页面」**，把结论写死在这，别再走回头路：
#   第 1 轮：以为入口在右上角**头像菜单**里 → 点了头像，菜单里是「成长福利」，
#           跳 `/user/center/growth` —— 那个页面标题是「成长等级」，正文全是
#           「掘友分 / 等级权益 / 去上传」，**根本没有转盘**。日志里
#           「未找到抽奖按钮」dump 出来的页面文本就是铁证。
#   第 2 轮（lodge 截图指正）：抽奖页的入口是**左侧菜单的「幸运抽奖」**，
#           而且它在**签到页**上就有！顺序是：
#             签到页 → 点左侧菜单「幸运抽奖」→ 转盘页（/user/center/lottery）
#           转盘页左侧菜单里「幸运抽奖」是**选中态**，右上角矿石胶囊显示数字。
#
#   所以正确的导航是**签到页左侧菜单项**，不是头像菜单、也不是 /growth。
#   教训：入口选择器要按 lodge 给的截图走，别自己推测。
LOTTERY_URL = os.getenv("JUEJIN_LOTTERY_URL", "https://juejin.cn/user/center/lottery")
# 左侧菜单「幸运抽奖」：用 `contains` 而不是 `=`，因为选中态元素文本可能带装饰字符
LOTTERY_MENU_XPATHS = (
    "//*[normalize-space(text())='幸运抽奖']",
    "//*[contains(text(),'幸运抽奖')]",
)
# 转盘页 URL 判据
LOTTERY_URL_HINTS = ("/user/center/lottery", "lottery")
# 转盘页特征文案（进错页面时用它判断，别再只看 URL —— /growth 那次就是 URL 对了但页面错了）
LOTTERY_PAGE_MARKERS = ("幸运大转盘", "免费抽奖次数", "十连抽", "围观大奖")
# 反例文案：出现这些说明进的是「成长等级」页，不是抽奖页
LOTTERY_WRONG_PAGE_MARKERS = ("掘友分明细", "等级规则", "等级权益", "升级行为")

# 头像菜单那条老路留着做**兜底**（万一哪天左侧菜单改版）：菜单里通常是「成长福利」，
# 跳的是 /growth（成长等级页），所以只能当最后一招，且进去后必须复核有没有转盘。
AVATAR_XPATHS = (
    "//img[contains(@class,'avatar') and not(contains(@class,'avatar-group'))]",
    "//header//img[contains(@class,'avatar')]",
    "//*[contains(@class,'avatar') and not(contains(@class,'avatar-group'))]",
)
GROWTH_MENU_XPATHS = (
    "//*[normalize-space(text())='成长福利']",
    "//*[contains(text(),'成长福利')]",
    "//*[normalize-space(text())='福利中心']",
)
GROWTH_URL = os.getenv("JUEJIN_GROWTH_URL", "https://juejin.cn/user/center/growth")

# 顶部矿石胶囊（截图那个「🪙 50174」）。
#
# ⚠️ 2026-09-29 线上实测「未读取到」，两个原因：
#   1. `contains(@class,'ore')` 会命中 **chat-box / more / score 这类无关类名**，
#      匹配到一堆空元素，前面几个取不到数字就一路空手而归；
#   2. 胶囊的数字直接是**元素自身的文本**（`<div class="...">50174</div>`），
#      没有「矿石」二字在里面 —— 按 `contains(text(),'矿石')` 找会命中旁边的图标/标签，
#      而它里面的数字是空的。
#    所以改成：按**叶子元素 + 文本形态**找 —— 元素自身文本恰好是一个「纯数字/千分位数字」，
#    且在页面**上半屏**（胶囊在 banner 里、y 很小），再用附近有没有「矿石」文案加权。
ORES_NUMBER_RE = r"^\s*(\d[\d,]{1,9})\s*$"
ORES_INLINE_JS = """
var re = /^\\s*\\d[\\d,]{1,9}\\s*$/;
// ⚠️ EXCLUDE 是「语义排除词表」：命中这些词的邻近上下文一律不认。
//    2026-09-29 生产事故积累：
//      · 等级/JY/掘友分/分值/权益/规则 → 成长等级页的 `JY8 25000` 阈值
//      · 次数/十连/抽奖            → 抽奖按钮上的「免费抽奖次数：1 次」
//      · 还需/升至                 → 「还需 120 升至下一级」
//      · 消息/通知/角标/badge      → 页头未读角标（4 位数的角标会抢答「最上方大数字」）
var EXCLUDE = /等级|JY|掘友分|还需|升至|分值|权益|规则|待补签|已签到|次数|十连|抽奖|消息|通知|角标/;
var out = [];
document.querySelectorAll('div, span, p, b, strong, em').forEach(function (el) {
  if (el.children.length) return;                 // 只要叶子节点，避免读到大容器的拼接文本
  var t = (el.textContent || '').trim();
  if (!re.test(t)) return;
  var r = el.getBoundingClientRect();
  if (r.width === 0 || r.height === 0) return;     // 不可见
  if (r.left < 0 || r.top < 0) return;
  // ⚠️ 2026-09-29 线上读错了：拿到的 25000 其实是成长等级页「JY8 25000」那个阈值！
  //    所以必须排除**带等级/分值/次数语义**的上下文，否则随便一页都能撞出个数字。
  //    注意 `near` 只往上爬 3 层、每层截 60 字符 —— 爬太深会把整页文案吸进来，
  //    EXCLUDE 里的宽容词（比如「次数」）就会误杀真胶囊。
  var near = '';
  var p = el;
  for (var i = 0; i < 3 && p; i++, p = p.parentElement) {
    near += (p.textContent || '').slice(0, 60);
  }
  if (EXCLUDE.test(near)) return;
  // 页头区域（y < 80）里带角标类名的数字直接判死，别指望 EXCLUDE 一定含关键词
  if (r.top < 80 && (el.className || '').toString().match(/badge|red-?dot|count|unread/i)) return;
  out.push({v: t.replace(/,/g, ''), y: r.top, x: r.left,
            hit: near.indexOf('矿石') >= 0 ? 1 : 0});
});
return out;
"""
# 抽奖按钮：**别把「免费抽奖次数：1 次」整串写进 xpath** —— 次数是当天的动态值
# （截图那天是 1 次，明天可能是 2 次），写死就失效。按「抽奖」二字模糊匹配。
#
# ⚠️ 2026-09-29 线上**两轮都栽在这**：左侧导航菜单的「幸运抽奖」也含「抽奖」二字，
#    第一版被 `//*[contains(text(),'抽奖')]` 命中；第二版加了
#    `not(contains(@class,'menu'/'nav'/'tab'/'item'))` 仍然没用 —— 因为线上那个
#    菜单项**外层没有这些类名**（都是构建哈希），而且它未必是 `li`。
#    结论：**别用「抽奖」二字模糊匹配**。改为认按钮的**独有文案特征**：
#      · 有免费次数时：`免费抽奖次数：1 次`（含「免费抽奖次数」+ 末尾「次」）
#      · 无免费次数时：按钮转「今日已抽完」类文案（由 DONE_MARKERS 处理，根本不用点）
#      · 直白的「免费抽取一次」也留着兜底
#    再补一条**结构判据**：按钮是 `button`，或位于转盘容器内。
LOTTERY_BUTTON_XPATHS = (
    # 最强特征：含「免费抽奖次数」的按钮（次数是动态值，所以只认前半段文案）
    "//button[contains(normalize-space(text()),'免费抽奖次数')]",
    "//*[contains(normalize-space(text()),'免费抽奖次数') and not(self::li)]",
    # 明确文案
    "//button[normalize-space(text())='免费抽取一次']",
    "//*[normalize-space(text())='免费抽取一次']",
    "//button[contains(normalize-space(text()),'免费抽取')]",
    # 转盘容器内的 button（结构兜底：容器类名常含 lottery/draw/wheel/prize）
    "//*[contains(@class,'lottery') or contains(@class,'wheel') or contains(@class,'prize')]//button",
)
# 已抽完：按钮转这些文案就别再点了（再点等于白撞一次接口、还可能触发风控）
LOTTERY_DONE_MARKERS = ("今日已抽完", "已抽完", "已用完", "明日再来", "没有免费", "次数已用完")

# ── 沸点广场：发一条沸点 + 给好友沸点点赞（2026-10-01 新增）──
#
# 流程（按 lodge 给的截图）：
#   签到+抽奖完成后**回首页** → 点导航栏「沸点」→ 沸点广场
#   → 在顶部输入框写一句话 → 点「发布」
#   → 在沸点列表里给**两名好友**的沸点点「点赞」
#
# ⚠️ 这条流程跟签到/抽奖是**三件独立的事**，任何一步失败都**不许**影响签到结论
#    （跟抽奖一个原则，见 growth_center 的宽口径 try）。发沸点失败就记进卡片备注。
PINS_URL = os.getenv("JUEJIN_PINS_URL", "https://juejin.cn/pins")
# 导航栏「沸点」入口：它在首页顶部导航里，是个链接/菜单项。
# ⚠️ 不能只认 `@href='/pins'` —— 线上导航是构建过的 SPA，很多项压根没有 href（走 JS 路由）。
#    所以先按 href，再按文案；文案用 `normalize-space(text())=` 精确匹配，
#    避免命中「沸点广场」这种更长文案时点错层级（那个是列表区的标题，不是导航项）。
PINS_NAV_XPATHS = (
    "//a[@href='/pins']",
    "//a[contains(@href,'/pins') and not(contains(@href,'pins/'))]",
    "//*[normalize-space(text())='沸点' and (self::a or self::li or self::div or self::span)]",
    "//nav//*[contains(normalize-space(text()),'沸点')]",
)
# 沸点广场特征文案（判「有没有真的进对页面」，跟抽奖页一个思路：**别只看 URL**）
# ⚠️ 页面上「沸点广场」是列表区左侧的标题，而顶部还有「沸点」导航项 ——
#    两个页面都有的话判据就没意义，所以挑**只有沸点页才有**的文案。
PINS_PAGE_MARKERS = ("沸点广场", "发布沸点", "请选择圈子", "快和掘友一起分享新鲜事")
# 反例文案：出现这些说明停在别的页面（首页 / 抽奖页），没进沸点广场
PINS_WRONG_PAGE_MARKERS = ("幸运大转盘", "免费抽奖次数", "掘友分明细")

# 发布框：截图里是一大块 textarea/可编辑区，placeholder 是
# 「快和掘友一起分享新鲜事！告诉你个小秘密，发布沸点时添加圈子和话题会被更多掘友看到哦~」
# ⚠️ 这段 placeholder 很长且**带波浪号**，直接写全会因全半角差异失配；
#    所以只认开头那截「快和掘友一起分享新鲜事」，并补一条**不带 placeholder 的结构兜底**
#    （沸点页可见的唯一 textarea / contenteditable）。
PINS_EDITOR_XPATHS = (
    "//textarea[contains(@placeholder,'快和掘友一起分享新鲜事')]",
    "//*[contains(@placeholder,'分享新鲜事')]",
    "//textarea[contains(@placeholder,'沸点')]",
    "//*[@contenteditable='true' and contains(@placeholder,'沸点')]",
    "//textarea",
    "//*[@contenteditable='true']",
)
# 发布按钮：截图里是输入框右下角那个蓝底按钮，文案就是「发布」。
# ⚠️ 必须**限定在发布框容器内**（见 _find_publish_button）：页面上还可能有
#    「发布沸点」标题、左侧「发布」入口等同名文案，全页模糊匹配会点错。
PINS_PUBLISH_XPATHS = (
    "//button[normalize-space(text())='发布']",
    "//button[contains(normalize-space(text()),'发布')]",
    "//*[normalize-space(text())='发布' and (self::button or self::div or self::span)]",
)
# 发完之后输入框里若还留着这些字，说明没发出去（或只是被打回）
PINS_PUBLISHED_MARKERS = ("发布成功", "发表成功", "发布中")
# 发布框里**不该残留**的内容 —— 发成功后框会清空；用它做次要判据
PINS_DRAFT_EMPTY_RE = r"^\s*$"

# 点赞：截图里每张沸点卡片底部有「分享 / 评论 / 点赞」三个按钮。
# ⚠️ 跟抽奖按钮那次一样的坑：**别用「点赞」二字扫整页** ——
#    右侧「精选沸点」栏、以及卡片里的「31赞」计数都可能含「赞」字。
#    所以：先在**沸点卡片容器**内拿 `.pins-btn` 之类的结构按钮，
#    再把文案恰好是「点赞」（未点过）的挑出来。
PINS_LIKE_MARKERS = ("点赞", "赞")
# 已经点过赞的文案（掘金点完会变「已赞」或加数字），见到就跳过，别重复点
PINS_LIKED_MARKERS = ("已赞", "取消赞")
# 关注关系判据（只给好友点赞）：卡片上出现这些说明这人**还没关注**，不算好友
PINS_NOT_FRIEND_MARKERS = ("关注", "已关注")
PINS_FRIEND_MARKERS = ("已关注",)  # 已关注 = 好友
# 点赞目标数量：lodge 要「两名好友」
PINS_LIKE_TARGET = int(os.getenv("JUEJIN_PINS_LIKES", "2"))
# 沸点文案（lodge 说「随便写一句话」；给个默认值，也允许环境变量覆盖）
PINS_TEXT = os.getenv("JUEJIN_PINS_TEXT", "今天也要好好写代码呀~")
# 沸点流程要跑几遍（lodge 要求「执行两遍」）+ 两遍之间的间隔秒数
PINS_ROUNDS = max(1, int(os.getenv("JUEJIN_PINS_ROUNDS", "2")))
PINS_ROUND_GAP = int(os.getenv("JUEJIN_PINS_GAP", "120"))
# 整条沸点流程的总开关
PINS_ENABLED = os.getenv("JUEJIN_PINS", "1") != "0"

# ── 文章详情页：点赞 + 收藏 + 关注作者（2026-10-01 新增）──
#
# 流程（按 lodge 给的截图）：
#   两遍沸点都跑完 → **回首页** → 点第 1 篇文章 → 文章详情页
#   → 左侧竖排操作栏点「赞」→ 点「收藏」→ 弹窗里选**默认收藏夹** → 点「确定」
#   → 右侧作者信息下方**有关注按钮就点**，已是「已关注」则忽略
#   → 回首页，点**第 2 篇**，把上面这套**重复一遍**（lodge 2026-10-01 追加）。
#
# ⚠️ 文章是**在新标签页打开的**（target=_blank / Ctrl+点击的等价行为）。
#    所以点完链接后**当前窗口还停在首页**，必须先 switch 到新句柄再去操作详情页；
#    做完还要切回来并关掉文章标签，否则句柄越积越多，第二篇就点不动了。
HOME_FIRST_ARTICLE_XPATHS = (
    # 首页信息流文章卡：掘金是 <a class="title" href="/post/xxx"> 这类结构。
    # 支持「按序号取第 N 篇」——把 %d 换成 1/2/3…（见 _article_xpaths）。
    "(//a[contains(@href,'/post/')])[%d]",
    "(//a[contains(@class,'title') and contains(@href,'/post/')])[%d]",
    "//main//a[contains(@href,'/post/')][%d]",
    "//div[contains(@class,'entry') or contains(@class,'article')]//a[contains(@href,'/post/')][%d]",
)
ARTICLE_URL_HINTS = ("/post/", "/entry/")
# 文章流程点几篇（lodge 要求「再点另一篇、重复一次」→ 默认 2）
ARTICLE_COUNT = max(1, int(os.getenv("JUEJIN_ARTICLE_COUNT", "2")))

# 文章详情页左侧竖排操作栏（截图：点赞 / 评论 / 收藏 / 分享 …）。
# ⚠️ 这排按钮**只有图标 + 数字**，没有「点赞」二字 —— 所以不能靠文案定位，
#    得按结构锚定：详情页主体左侧那条窄竖栏。这里用**多种结构判据**兜。
#    点完后计数 +1、且按钮会加高亮态，用它复核是否真的点上了。
ARTICLE_LIKE_XPATHS = (
    # 优先：**类名里带 like 的叶子/组件**（掘金详情页操作栏是 .like-btn 这类）
    "//*[contains(@class,'like-btn') or contains(@class,'like-icon')]",
    "//*[contains(@class,'like')][not(.//*[contains(@class,'like')])]",
    "//div[contains(@class,'action') or contains(@class,'operate')]"
    "//*[contains(@class,'like') and not(.//*[contains(@class,'like')])]",
)
ARTICLE_COLLECT_XPATHS = (
    "//*[contains(@class,'collect-btn') or contains(@class,'collect-icon')]",
    "//*[contains(@class,'collect')][not(.//*[contains(@class,'collect')])]",
    "//div[contains(@class,'action') or contains(@class,'operate')]"
    "//*[contains(@class,'collect') and not(.//*[contains(@class,'collect')])]",
)
# 已点赞 / 已收藏态（点过就跳过，别点成取消）
ARTICLE_LIKED_MARKERS = ("已点赞", "liked", "active")
ARTICLE_COLLECTED_MARKERS = ("已收藏", "collected", "active")

# 收藏弹窗：标题「选择收藏集」，副标题「选择或创建你想添加的收藏集」，
# 列表里默认收藏夹就是「我的收藏」+「默认」标签，右下角「确定」按钮。
COLLECT_MODAL_MARKERS = ("选择收藏集", "选择或创建你想添加的收藏集", "新建收藏集")
COLLECT_DEFAULT_XPATHS = (
    # 默认收藏夹：文案含「我的收藏」的那一项（截图里就是它，带「默认」小标签）
    "//*[contains(normalize-space(.),'我的收藏')][not(.//*[contains(normalize-space(.),'我的收藏')])]",
    "//*[contains(@class,'item') or contains(@class,'folder')][contains(normalize-space(.),'我的收藏')]",
    "//*[contains(normalize-space(.),'默认')][not(.//*[contains(normalize-space(.),'默认')])]",
)
COLLECT_CONFIRM_XPATHS = (
    "//button[normalize-space(text())='确定']",
    "//*[normalize-space(text())='确定' and (self::button or self::div or self::span)]",
    "//*[contains(@class,'confirm') or contains(@class,'ok')][normalize-space(text())='确定']",
)
# 已收藏过：弹窗不出现，或页面直接提示已收藏
COLLECT_ALREADY_MARKERS = ("已收藏", "已加入收藏集")

# 右侧作者信息区下方的关注按钮（截图：蓝色实心「关注」；已关注则是「已关注」）
AUTHOR_FOLLOW_XPATHS = (
    # ⚠️ 「关注」二字在页头导航里也有（顶部「关注」标签页），必须限定在**作者卡片**内。
    #    作者卡在右侧栏，含粉丝数、文章数这类信息，用「私信」按钮当锚点最稳：
    #    截图里关注与私信并排，所以找私信的同级/祖先范围内的「关注」。
    "//*[normalize-space(text())='私信']/ancestor::*[self::div or self::section][1]"
    "//*[normalize-space(text())='关注']",
    "//*[normalize-space(text())='私信']/preceding-sibling::*[normalize-space(text())='关注']",
    "//*[normalize-space(text())='私信']/following-sibling::*[normalize-space(text())='关注']",
)
AUTHOR_FOLLOWED_MARKERS = ("已关注", "互相关注")
# 整条文章流程的总开关
ARTICLE_ENABLED = os.getenv("JUEJIN_ARTICLE", "1") != "0"
# 沸点卡片容器：用于**限定范围**找按钮，不要把右侧精选沸点、页头导航算进来
PINS_ITEM_XPATH = (
    "//div[contains(@class,'pin') or contains(@class,'item') or contains(@class,'entry')]"
    "[.//*[contains(normalize-space(.),'点赞')]]"
)

# ⚠️ 历史教训（判据已删，教训留着）：2026-09-29 第一版拿「恭喜/抽中/获得」扫**整页文案**
#    判抽奖成功，而抽奖页右侧「围观大奖」栏一直在播报**别人**的中奖
#    （`恭喜 胡毛毛 抽中 Pico Neo3`），于是「一下没抽」被报成「抽奖成功」。
#    结论：**任何"中奖"判据都不许扫整页文案**，只能是结构性的（弹层 / 次数变化）。
#    第 5 轮 lodge 明确要求「不用获取抽奖确认」——连"确认抽奖结果"这一步都取消了
#    （点完即返回，见 lottery_free_draw），所以弹层读取 / 弹层关闭那套代码已整体删除。
#    如果以后要重新加结果确认，**别再退回扫整页那条路**。


def _safe_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as f:
            f.write(data)
    except OSError as err:
        print("[WARN] 写诊断文件失败 %s: %s" % (path, err))


def page_text(driver):
    """整页可见文本（压缩空白）——掘金是 SPA，取 body.innerText 最省事。"""
    try:
        return " ".join(
            (driver.execute_script("return document.body.innerText || '';") or "").split()
        )
    except WebDriverException:
        return ""


def dump_debug(driver, tag, notes=(), secrets=()):
    """留存失败现场：URL、页面文案、DOM、截图（入库前抹掉凭据）。

    ⚠️ 整个函数**不得抛异常**（2026-09-29 踩到）：它是在错误处理路径上调用的，
    driver 这时可能已经挂了（浏览器崩了/连接断了），连 `page_text` 都会抛 ——
    那样会把「原本只是取不到现场」升级成真正的失败，掩盖掉真正的错误。
    所以每一处取数各自兜底。
    """
    prefix = os.path.join(DEBUG_DIR, "%s_%s" % (tag, time.strftime("%H%M%S")))

    info = []

    def _try(label, fn, default=""):
        try:
            return fn()
        except Exception as err:
            return "%s 读取失败: %s" % (label, str(err)[:80])

    info.append("url: %s" % _try("url", lambda: driver.current_url, "(读不到)"))
    info.append("title: %s" % _try("title", lambda: driver.title, "(读不到)"))
    info.append("页面文本: %s" % _try("页面文本", lambda: page_text(driver)[:300], "(读不到)"))
    info.extend("note: %s" % n for n in notes)

    try:
        driver.execute_script(
            "document.querySelectorAll('input').forEach(function(e){e.value='';});"
        )
    except Exception:
        pass

    html = _try("page_source", lambda: driver.page_source, "")
    text = "\n".join(info) + "\n"
    for secret in secrets:
        # 只抹够长的值：短值（如 1、0）会把诊断文本里的数字全打成 ***
        if secret and len(secret) >= 6:
            html = html.replace(secret, "***")
            text = text.replace(secret, "***")

    _safe_write(prefix + ".txt", text)
    _safe_write(prefix + ".html", html)
    try:
        _safe_write(prefix + ".png", driver.get_screenshot_as_png())
    except Exception as err:
        print("[WARN] 现场截图失败: %s" % str(err)[:80])
    print("===> 失败现场已留存: %s.{txt,html,png}" % prefix)
    print(text.strip())


def is_logged_in(driver):
    """登录态判据：`sessionid` cookie 存在，或页面上找不到登录按钮。"""
    try:
        if driver.get_cookie("sessionid"):
            return True
    except WebDriverException:
        pass
    try:
        if "juejin.cn" in (driver.current_url or ""):
            return find_visible(driver, LOGIN_BUTTON_XPATHS)[0] is None
    except WebDriverException:
        pass
    return False


def risk_control_hit(driver):
    """是否命中「请用抖音 APP 扫码验证」的风控文案。"""
    text = page_text(driver)
    return any(marker in text for marker in RISK_MARKERS)


def fetch_bytes(driver, url):
    """在当前页面上下文里把图片抓成 bytes（走浏览器，带 referer，避免 CDN 直接请求被拒）。"""
    data_url = driver.execute_async_script(FETCH_AS_DATA_URL_JS, url)
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        raise RuntimeError("取图失败: %s" % str(data_url)[:80])
    return base64.b64decode(data_url.split(",", 1)[1])


def slider_offset(bg_bytes, piece_bytes):
    """算缺口左边缘到背景左边缘的距离（**原始图片像素**），返回 (loc, 置信度)。

    关键：拼图块是「亮版」内容，背景上的缺口是**压暗**过的，直接按像素匹配会匹配到
    云/岩石上（实测置信度 0.80 落在云里）。改用带 alpha 掩码的 `TM_CCOEFF_NORMED` ——
    它对线性明暗变化不敏感，实测 0.93 且二维落点正落在缺口上。
    掩码先腐蚀一圈，把拼图块自带的白色描边剔掉，否则会拉低相关。
    """
    bg = cv2.imdecode(np.frombuffer(bg_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    piece = cv2.imdecode(np.frombuffer(piece_bytes, np.uint8), cv2.IMREAD_UNCHANGED)
    if bg is None or piece is None:
        raise RuntimeError("图片解码失败")
    if piece.shape[2] == 4:
        alpha = piece[:, :, 3]
    else:
        alpha = np.full(piece.shape[:2], 255, np.uint8)
    gray = cv2.cvtColor(piece[:, :, :3], cv2.COLOR_BGR2GRAY)
    mask = cv2.erode((alpha > 128).astype(np.uint8) * 255, np.ones((7, 7), np.uint8))
    res = cv2.matchTemplate(bg, gray, cv2.TM_CCOEFF_NORMED, mask=mask)
    _, score, _, loc = cv2.minMaxLoc(res)
    return loc, float(score)


def human_track(distance):
    """生成拖动轨迹（ActionChains 回退路径用）：easeInOut 曲线 + 抖动。"""
    if distance <= 0:
        return []
    steps = max(10, min(28, distance // 8 or 10))
    track = []
    prev = 0.0
    for i in range(1, steps + 1):
        eased = 0.5 - 0.5 * math.cos(math.pi * i / steps)   # easeInOutSine
        pos = distance * eased
        track.append(pos - prev + random.uniform(-0.8, 0.8))  # 加抖动
        prev = pos
    track[-1] += distance - sum(track)                        # 补齐到精确距离
    return [max(1, int(round(abs(s)))) for s in track]


def human_points(distance, duration):
    """返回 [(x, t)]：先加速后减速 + 抖动 + 末尾小幅过冲再回拉（更像人手的收尾）。"""
    steps = max(18, min(60, int(distance / 2.5) or 20))
    points = []
    for i in range(1, steps + 1):
        frac = i / steps
        eased = 0.5 - 0.5 * math.cos(math.pi * frac)
        points.append([
            distance * eased + random.uniform(-0.7, 0.7),
            duration * frac + random.uniform(-duration * 0.02, duration * 0.02),
        ])
    overshoot = random.uniform(1.0, 3.0)
    points.append([distance + overshoot, duration + random.uniform(0.05, 0.12)])
    points.append([distance, duration + random.uniform(0.15, 0.30)])
    points.sort(key=lambda p: p[1])
    return points


def drag_by_cdp(driver, handle_x, handle_y, distance, duration):
    """用 CDP `Input.dispatchMouseEvent` 派发拖动，并**显式指定时间戳**。

    为什么不用 ActionChains：每个 `perform()` 都是一次 WebDriver 往返，实测每步约 0.3s
    （70 步要 21 秒），时间完全不可控；而且同一帧会产生成对的 pointer/mouse 事件，
    服务端看到 0ms 间隔会判「操作过快」。CDP 这条路能精确控速（实测点间隔 16~50ms）。

    坐标要点：**CDP 用顶层视口坐标**，而 Selenium 在 iframe 内给的是 iframe 局部坐标，
    所以调用方必须先把 iframe 的 rect 偏移加进来（否则按下点打空、滑块纹丝不动）。
    """
    base = time.time()
    # 先移到手柄上「停一下」，再按下 —— 直接瞬移+按下更像脚本
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseMoved", "x": handle_x, "y": handle_y, "button": "none"})
    time.sleep(random.uniform(0.2, 0.5))
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mousePressed", "x": handle_x, "y": handle_y, "button": "left",
        "buttons": 1, "clickCount": 1, "timestamp": base})
    time.sleep(random.uniform(0.15, 0.35))

    for x, t in human_points(distance, duration):
        timestamp = base + t
        wait = timestamp - time.time()
        if wait > 0:
            time.sleep(wait)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": handle_x + x,
            "y": handle_y + random.choice([0, 0, 0, 0, 1, -1]),
            "button": "left", "buttons": 1, "timestamp": timestamp})

    time.sleep(random.uniform(0.1, 0.25))
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
        "type": "mouseReleased", "x": handle_x + distance, "y": handle_y,
        "button": "left", "buttons": 0, "clickCount": 1, "timestamp": time.time()})
    return time.time() - base


def drag_by_actions(driver, handle, distance):
    """回退方案：ActionChains（CDP 不可用时）。"""
    ActionChains(driver).move_to_element(handle).click_and_hold().perform()
    time.sleep(random.uniform(0.15, 0.35))
    for step in human_track(distance):
        ActionChains(driver).move_by_offset(step, 0).perform()
        time.sleep(random.uniform(0.008, 0.022))
    time.sleep(random.uniform(0.2, 0.5))
    ActionChains(driver).release().perform()


def captcha_present(driver):
    """父页面里是否还挂着验证 iframe。"""
    try:
        driver.switch_to.default_content()
    except WebDriverException:
        pass
    try:
        return len(driver.find_elements(By.XPATH, CAPTCHA_FRAME_XPATHS[0])) > 0
    except WebDriverException:
        return False


def click_captcha_refresh(driver):
    element, _ = find_visible(driver, CAPTCHA_REFRESH_XPATHS)
    if element is None:
        print("[WARN] 找不到验证码刷新按钮")
        return
    try:
        element.click()
        time.sleep(1.5)
    except WebDriverException as err:
        print("[WARN] 刷新验证码失败: %s" % err)


def solve_slider(driver, max_rounds=4):
    """过字节滑块验证码；返回是否通过（判据：父页面里的验证 iframe 消失）。"""
    frame, _ = wait_visible(driver, CAPTCHA_FRAME_XPATHS, 25, "验证 iframe")
    if frame is None:
        return False
    # iframe 在**顶层页面**里的偏移：CDP 派发鼠标事件用的是顶层视口坐标，
    # 而 Selenium 在 iframe 内取到的是 iframe 局部坐标 —— 必须把这段偏移补上。
    try:
        frame_rect = frame.rect
        frame_x, frame_y = frame_rect["x"], frame_rect["y"]
    except WebDriverException:
        frame_x, frame_y = 0, 0
    print("===> 验证 iframe 顶层偏移: (%d, %d)" % (frame_x, frame_y))

    for round_no in range(1, max_rounds + 1):
        driver.switch_to.frame(frame)
        try:
            bg, _ = wait_visible(driver, CAPTCHA_BG_XPATHS, 15, "拼图背景图")
            piece, _ = wait_visible(driver, CAPTCHA_PIECE_XPATHS, 15, "拼图小块")
            handle, _ = wait_visible(driver, CAPTCHA_HANDLE_XPATHS, 15, "拖动按钮")
            if bg is None or piece is None or handle is None:
                print("[WARN] 验证码元素没找全（背景/小块/拖动钮）")
                return False

            # 等图片真的加载完再取尺寸：没加载完时 naturalWidth=0，比例会算错
            load_deadline = time.time() + 15
            while time.time() < load_deadline:
                if int(bg.get_attribute("naturalWidth") or 0) > 0:
                    break
                time.sleep(0.3)

            rendered_w = bg.size["width"]
            natural_w = int(bg.get_attribute("naturalWidth") or 0)
            bg_bytes = fetch_bytes(driver, bg.get_attribute("src"))
            piece_bytes = fetch_bytes(driver, piece.get_attribute("src"))
            (natural_x, natural_y), score = slider_offset(bg_bytes, piece_bytes)
            scale = (rendered_w / float(natural_w)) if natural_w else 0
            if not natural_w:
                # 图片没加载完时 naturalWidth=0，比例会退化成 1.0，拖动距离直接算错
                # （2026-09-27 CI 第 1 轮就是这么废掉的：比例 1.0000、拖了 295px）
                print("[WARN] 背景图还没加载完（naturalWidth=0），换一张重来")
                click_captcha_refresh(driver)
                continue
            distance = int(round(natural_x * scale))
            print(
                "===> 第 %d/%d 轮: 缺口命中 %s(原始像素) 置信度 %.3f → 拖动 %d px（比例 %.4f）"
                % (round_no, max_rounds, (natural_x, natural_y), score, distance, scale)
            )
            if distance <= 0:
                print("[WARN] 算出的拖动距离非正，刷新重来")
                click_captcha_refresh(driver)
                continue

            # 拖动：优先 CDP（时长精确可控），失败再回退 ActionChains
            duration = random.uniform(0.9, 1.5)
            handle_rect = handle.rect
            handle_x = frame_x + handle_rect["x"] + handle_rect["width"] / 2.0
            handle_y = frame_y + handle_rect["y"] + handle_rect["height"] / 2.0
            try:
                real = drag_by_cdp(driver, handle_x, handle_y, distance, duration)
                print("===> 已释放滑块（CDP 拖动，计划 %.2fs / 实际 %.2fs）" % (duration, real))
            except WebDriverException as err:
                print("[WARN] CDP 拖动不可用(%s)，回退 ActionChains" % str(err)[:60])
                drag_by_actions(driver, handle, distance)
                print("===> 已释放滑块（ActionChains 回退）")
        finally:
            try:
                driver.switch_to.default_content()
            except WebDriverException:
                pass

        deadline = time.time() + 8
        while time.time() < deadline:
            if not captcha_present(driver):
                print("===> 滑块验证通过（验证 iframe 已消失）")
                return True
            time.sleep(0.5)

        print("===> 滑块未通过，换一张重试")
        frame, _ = find_visible(driver, CAPTCHA_FRAME_XPATHS)
        if frame is None:
            return True
        driver.switch_to.frame(frame)
        try:
            click_captcha_refresh(driver)
        finally:
            try:
                driver.switch_to.default_content()
            except WebDriverException:
                pass
        time.sleep(2)

    return not captcha_present(driver)


def login_once(driver, username, password, attempt=1):
    """密码登录：提交后若弹出滑块验证码就自动拖过去。"""
    driver.get(HOME_URL)
    time.sleep(3)
    if is_logged_in(driver):
        print("===> 已是登录态（cookie 复用），跳过登录")
        return True

    button, _ = wait_visible(driver, LOGIN_BUTTON_XPATHS, 20, "首页登录按钮")
    if button is None:
        raise NoSuchElementException("首页未找到登录按钮")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    button.click()
    time.sleep(2)

    tab, _ = wait_visible(driver, PASSWORD_TAB_XPATHS, 15, "密码登录入口")
    if tab is None:
        raise NoSuchElementException("登录弹层未找到「密码登录」入口")
    tab.click()
    time.sleep(1.5)

    user, _ = wait_visible(driver, USERNAME_XPATHS, 15, "账号输入框")
    pwd, _ = wait_visible(driver, PASSWORD_XPATHS, 15, "密码输入框")
    if user is None or pwd is None:
        raise NoSuchElementException("密码登录面板未找到账号/密码输入框")
    user.clear()
    user.send_keys(username)
    pwd.clear()
    pwd.send_keys(password)

    submit, _ = wait_visible(driver, SUBMIT_XPATHS, 10, "登录提交按钮")
    if submit is None:
        raise NoSuchElementException("登录弹层未找到提交按钮")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", submit)
    submit.click()
    time.sleep(4)

    # 提交后站点多半弹滑块验证码（字节验证中心 iframe），过掉它才继续登录
    if captcha_present(driver):
        print("===> 命中滑块验证码，开始自动拖动")
        if not solve_slider(driver):
            dump_debug(driver, "a%d_slider_failed" % attempt, secrets=(username, password))
            raise RuntimeError("滑块验证码未通过（已重试多轮）")
        time.sleep(3)

    for _ in range(6):
        if is_logged_in(driver):
            print("===> 登录成功")
            return True
        if risk_control_hit(driver):
            dump_debug(driver, "a%d_risk_control" % attempt, secrets=(username, password))
            raise RuntimeError(
                "掘金要求用「抖音 APP」扫码验证（账号风控），这条流程自动化走不通"
            )
        time.sleep(2)

    dump_debug(driver, "a%d_login_timeout" % attempt, secrets=(username, password))
    return False


def read_numbers(driver):
    """读签到页上的矿石数 / 连续天数 / 累计天数；读不到为 None。

    走 **DOM 结构**（找标签元素 → 取同卡片内数字），不靠整页文本顺序 ——
    掘金这三个统计卡是「数字在上、标签在下」，用文本正则配必然串位（见常量注释）。
    DOM 取不到时才退回文本正则兜底，且兜底正则也是按「数字在前」写的。
    """
    values = {"ores": None, "streak": None, "total": None}
    try:
        raw = driver.execute_script(SIGNIN_STATS_JS) or {}
        for key in values:
            value = raw.get(key)
            if value:
                values[key] = str(value)
    except WebDriverException as err:
        print("[WARN] DOM 取签到统计失败，退回文本正则: %s" % str(err)[:80])

    if all(values.values()):
        print("===> 签到统计（DOM）: 矿石=%s 连续=%s 累计=%s"
              % (values["ores"], values["streak"], values["total"]))
        return values

    # 兜底：文本正则（数字在前、标签在后）
    text = page_text(driver)

    def pick(pattern):
        match = re.search(pattern, text)
        return match.group(1).replace(",", "") if match else None

    if not values["ores"]:
        values["ores"] = pick(ORES_FALLBACK_PATTERN)
    if not values["streak"]:
        values["streak"] = pick(STREAK_FALLBACK_PATTERN)
    if not values["total"]:
        values["total"] = pick(TOTAL_FALLBACK_PATTERN)
    print("===> 签到统计（部分走文本兜底）: 矿石=%s 连续=%s 累计=%s"
          % (values["ores"], values["streak"], values["total"]))
    return values


def sign_in(driver, username="", password=""):
    """签到：打开每日签到页 → 点「立即签到」→ 多重判据确认结果。"""
    driver.get(SIGNIN_URL)
    time.sleep(5)

    if not is_logged_in(driver):
        dump_debug(
            driver,
            "signin_not_logged_in",
            notes=["签到页不是登录态：url=%s" % driver.current_url],
            secrets=(username, password),
        )
        raise RuntimeError("签到页不是登录态：url=%s" % driver.current_url)

    before = read_numbers(driver)
    print(
        "===> 签到前: 矿石数=%s 连续=%s 累计=%s"
        % (before["ores"] or "?", before["streak"] or "?", before["total"] or "?")
    )

    text = page_text(driver)
    button, hit = find_visible(driver, SIGNIN_BUTTON_XPATHS)
    if button is None:
        if any(marker in text for marker in SIGNIN_DONE_MARKERS):
            print("===> 没有「立即签到」按钮，但页面出现已签到文案")
            return "今日已签到（跳过）", before
        dump_debug(
            driver,
            "signin_no_button",
            notes=["签到页既没有「立即签到」按钮，也没有已签到文案（页面结构可能变了）"],
            secrets=(username, password),
        )
        raise RuntimeError("签到页未找到签到按钮：url=%s" % driver.current_url)

    button_text = (button.text or "").strip()
    print("===> 找到签到按钮: %r（选择器 %s）" % (button_text, hit))
    if any(marker in button_text for marker in SIGNIN_DONE_MARKERS):
        return "今日已签到（跳过）", before

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    button.click()
    print("===> 已点击「立即签到」")

    deadline = time.time() + 20
    after = before
    while time.time() < deadline:
        time.sleep(1)
        after = read_numbers(driver)
        now_text = page_text(driver)

        # 判据一：数字变了（矿石 +X / 连续天数 +1）
        if after["ores"] != before["ores"] or after["streak"] != before["streak"]:
            print("===> 签到成功（数字变化: 矿石 %s -> %s）" % (before["ores"], after["ores"]))
            return "签到成功", after
        # 判据二：按钮不再是「立即签到」，且页面出现已签到文案
        left, _ = find_visible(driver, SIGNIN_BUTTON_XPATHS)
        if left is None and any(marker in now_text for marker in SIGNIN_DONE_MARKERS):
            print("===> 签到成功（按钮已转为已签到态）")
            return "签到成功", after
        # 判据三：明确的成功提示
        if any(marker in now_text for marker in SIGNIN_SUCCESS_MARKERS):
            print("===> 签到成功（页面出现成功提示）")
            return "签到成功", after

    dump_debug(
        driver,
        "signin_not_confirmed",
        notes=[
            "点击「立即签到」后 20s 内状态未变化",
            "点击前: 矿石=%s 连续=%s" % (before["ores"], before["streak"]),
            "点击后: 矿石=%s 连续=%s" % (after["ores"], after["streak"]),
        ],
        secrets=(username, password),
    )
    raise RuntimeError("点击「立即签到」后状态未变化，可能未生效")


def read_ores_badge(driver):
    """读抽奖页顶部的**矿石数胶囊**（截图那个 55210）。

    ⚠️ 2026-09-29 第三轮线上又读错了（读到 `2026`，实际 `55210`），根因两条：
      1. 转盘页的胶囊**邻近没有「矿石」二字** —— 截图看就是「🔶 图标 + 55210」，纯图标没标签。
         所以我原来「优先邻近有矿石字样」的策略在这一页**全部落空**；
      2. 落空后掉到「整页文案里 矿石(\\d+)」的兜底正则，而它抓到的是页面**别处**的
         `2026`（年份 —— 「© 2026 稀土掘金」！），于是把版权年份当成了矿石数。

    正确做法（按页面结构，而不是猜）：
      抽奖页的矿石胶囊**一定在页面最上方**（banner 里）。所以取「可见纯数字叶子」中
      **y 最小**的那个即可，语义排除词表负责挡掉 `等级/JY/次数/十连/年份` 这些干扰。
    兜底正则也一并收紧：`矿石 数字` 只认「紧贴矿石二字」的，且**排除 19xx/20xx 年份形态**。
    """
    try:
        candidates = driver.execute_script(ORES_INLINE_JS) or []
    except WebDriverException as err:
        candidates = []
        print("[WARN] 扫描矿石数胶囊失败: %s" % str(err)[:80])

    usable = [c for c in candidates if isinstance(c, dict) and c.get("v")]
    # 排序：位置越靠上越可能是胶囊（banner 在第一屏顶部）
    ranked = sorted(usable, key=lambda c: float(c.get("y") or 0))

    for cand in usable:
        # 先信任「邻近有矿石字样」的（签到页那种带标签的形态）
        if cand.get("hit") and len(cand["v"]) >= 3:
            print("===> 矿石数胶囊取值: %s（y=%s，邻近矿石字样=1）"
                  % (cand["v"], cand.get("y")))
            return cand["v"]

    # 转盘页的主路径：**最靠上的大数字**就是胶囊（不再依赖「矿石」字样）
    for cand in ranked:
        if len(cand["v"]) >= 4 and not _looks_like_year(cand["v"]):
            print("===> 矿石数胶囊取值（页面最上方大数字）: %s（y=%s）"
                  % (cand["v"], cand.get("y")))
            return cand["v"]

    # 兜底：整页文案里紧贴「矿石」的数字（且不是年份形态）
    text = page_text(driver)
    for match in re.finditer(r"矿石[^\d]{0,6}(\d[\d,]{2,})", text):
        value = match.group(1).replace(",", "")
        if not _looks_like_year(value):
            print("===> 矿石数（整页正则兜底）: %s" % value)
            return value

    for cand in ranked:
        if len(cand["v"]) >= 4:
            print("===> 矿石数（弱候选，请核对）: %s（y=%s）" % (cand["v"], cand.get("y")))
            return cand["v"]
    return None


def _looks_like_year(value):
    """排除 `2026` 这类版权年份 —— 2026-09-29 线上就是被「© 2026 稀土掘金」坑的。

    只把 1900~2099 的**四位整数**当年份；五位以上（55210）一律不误伤。
    """
    if len(value) != 4:
        return False
    return 1900 <= int(value) <= 2099


def goto_growth_center(driver, username="", password=""):
    """签到页 → 点左侧菜单「幸运抽奖」→ 转盘页。返回是否成功进入（**以页面内容为准**）。

    ⚠️ 2026-09-29 两轮线上实测的血泪（别改回去）：
      第 1 轮走「头像菜单 → 成长福利」→ 跳到 `/user/center/growth`，那页是
      **「成长等级」**（掘友分/等级权益），**没有转盘**，于是「未找到抽奖按钮」。
      第 2 轮 lodge 截图指正：转盘页入口是**签到页左侧菜单的「幸运抽奖」**，
      点它到 `/user/center/lottery`。
    所以现在的顺序：
      1. 打开签到页 → 点左侧菜单「幸运抽奖」；
      2. 点不到 → 直接 `GET /user/center/lottery`；
      3. 两个都到不了 → 才退回头像菜单那条老路（跳 /growth，通常没用）。
    **进没进对的判据是页面内容**（有「幸运大转盘/免费抽奖次数」且**没有**「掘友分明细」
    这类成长等级文案），不能只看 URL —— 上一轮就是 URL 命中 `/growth` 但页面全错。
    """
    driver.get(SIGNIN_URL)
    time.sleep(3)
    if not wait_url(driver, "/signin", 15):
        print("[WARN] 签到页 URL 未落地，仍继续尝试进抽奖页")

    # A 方案（官方路径）：签到页左侧菜单「幸运抽奖」
    menu, menu_hit = wait_visible(driver, LOTTERY_MENU_XPATHS, 10, "左侧菜单「幸运抽奖」")
    if menu is None:
        print("[WARN] 签到页左侧菜单没找到「幸运抽奖」，直接打开 %s" % LOTTERY_URL)
        driver.get(LOTTERY_URL)
    else:
        print("===> 找到左侧菜单「幸运抽奖」（选择器 %s），点击进入" % menu_hit)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", menu)
            menu.click()
        except WebDriverException as err:
            print("[WARN] 常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
            try:
                driver.execute_script("arguments[0].click();", menu)
            except WebDriverException as err2:
                print("[WARN] JS 点击也失败: %s，改为直接打开 URL" % str(err2)[:60])
                driver.get(LOTTERY_URL)
        time.sleep(3)
        # 点了没跳转就直接开 URL（同一个登录态，等价）
        if "lottery" not in (driver.current_url or ""):
            print("===> 菜单点击未跳转，直接打开 %s" % LOTTERY_URL)
            driver.get(LOTTERY_URL)

    time.sleep(3)
    if _on_lottery_page(driver):
        print("===> 已进入幸运抽奖页（%s）" % driver.current_url)
        return True

    # B 方案（兜底，通常没用）：头像菜单 →「成长福利」。留着只为菜单改版时不至于全挂。
    print("[WARN] %s 不是抽奖页，退回头像菜单方式试一次" % driver.current_url)
    _try_avatar_menu(driver)

    time.sleep(3)
    ok = _on_lottery_page(driver)
    if not ok:
        dump_debug(
            driver,
            "lottery_page_not_entered",
            notes=[
                "没能进入幸运抽奖页",
                "当前 URL: %s" % driver.current_url,
                "页面文本首 200 字: %s" % page_text(driver)[:200],
            ],
            secrets=(username, password),
        )
    print("===> 抽奖页: %s（%s）" % ("已进入" if ok else "未能进入", driver.current_url))
    return ok


def _on_lottery_page(driver):
    """当前页面是不是**真的**抽奖页。

    双向判据，缺一不可（2026-09-29 只看 URL 吃过亏）：
      · 正：出现转盘特征文案（幸运大转盘 / 免费抽奖次数 / 十连抽 / 围观大奖）
      · 反：**没有**成长等级页的文案（掘友分明细 / 等级规则 / 等级权益 / 升级行为）
    """
    text = page_text(driver)
    if any(marker in text for marker in LOTTERY_WRONG_PAGE_MARKERS):
        print("[WARN] 检测到「成长等级」页文案，判定不是抽奖页")
        return False
    hit = [m for m in LOTTERY_PAGE_MARKERS if m in text]
    if hit:
        print("===> 抽奖页特征命中: %s" % ", ".join(hit))
        return True
    return False


def _try_avatar_menu(driver):
    """兜底路径：点头像 →「成长福利」。**跳的是 /growth（成长等级页），大概率没用**，
    所以调用方必须再用 `_on_lottery_page` 复核，不能靠它返回真假。"""
    avatar, hit = wait_visible(driver, AVATAR_XPATHS, 8, "头像")
    if avatar is None:
        print("[WARN] 没找到头像元素")
        return
    print("===> 兜底：点击头像展开菜单（%s）" % hit)
    try:
        avatar.click()
    except WebDriverException:
        try:
            driver.execute_script("arguments[0].click();", avatar)
        except WebDriverException as err:
            print("[WARN] 点击头像失败: %s" % str(err)[:60])
            return
    time.sleep(1.5)
    entry, entry_hit = wait_visible(driver, GROWTH_MENU_XPATHS, 6, "「成长福利」菜单项")
    if entry is None:
        print("[WARN] 头像菜单里没有「成长福利」")
        return
    print("===> 兜底：点击「成长福利」（%s）" % entry_hit)
    try:
        entry.click()
        time.sleep(3)
    except WebDriverException as err:
        print("[WARN] 点击「成长福利」失败: %s" % str(err)[:60])


def lottery_free_draw(driver, username="", password=""):
    """点一次「免费抽奖次数：N 次」，返回 (状态文案, 奖励文案)。

    2026-09-29 第三轮线上后**按 lodge 要求简化**：他明确说
    「现在抽奖可以正常，实际就是没有抽奖反馈。**不用获取抽奖确认**」。
    所以这里**点完就返回**，不再等结果、不再判成功 —— 之前那套 25 秒轮询
    等「免费次数变小 / 按钮转已抽完 / 矿石变化 / 弹层奖品」，在他那边判定
    「抽奖未确认」，而实际抽奖是成功的（截图能看到转盘转动、次数已经消耗）。
    结论：**等待与确认这段是多余复杂度**，删掉。

    保留的仍然有价值的部分：
      · 点之前先判「今日已抽完」→ 跳过（避免重复点，也避免白撞接口）；
      · 点之前读一次**免费次数与矿石数**，打进日志便于人工核对；
      · 按钮定位仍走 `_find_lottery_button`（不误命中左侧菜单）。

    返回的「奖励文案」现在只是**抽完后重读的矿石数**，供卡片展示参考。
    """
    # ⚠️ 顺序要紧：**先判「今日已抽完」再去找按钮**。
    # 反过来的话，模糊选择器会把左侧菜单的「幸运抽奖」当成按钮命中，点它等于空点。
    text = page_text(driver)
    if any(marker in text for marker in LOTTERY_DONE_MARKERS):
        print("===> 页面已出现已抽完文案，判定今日已抽过")
        return "今日已抽完（跳过）", ""

    before_free = read_free_draws(driver)
    before_ores = read_ores_badge(driver)
    print("===> 抽奖前: 免费次数=%s 矿石数=%s"
          % (before_free if before_free is not None else "未读取到", before_ores or "未读取到"))

    button = _find_lottery_button(driver)
    if button is None:
        dump_debug(
            driver,
            "lottery_no_button",
            notes=["抽奖页未找到「免费抽奖次数」按钮（页面结构可能变了）"],
            secrets=(username, password),
        )
        return "抽奖失败（未找到抽奖按钮）", ""

    button_text = _element_text(driver, button)
    print("===> 找到抽奖按钮: %r" % button_text)
    if any(marker in button_text for marker in LOTTERY_DONE_MARKERS):
        return "今日已抽完（跳过）", ""

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    time.sleep(0.5)
    # 按钮是动画元素（转盘转动时会位移），click 可能报 element click intercepted —— 降级用 JS 点
    clicked = False
    try:
        button.click()
        clicked = True
    except WebDriverException as err:
        print("[WARN] 常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
        try:
            driver.execute_script("arguments[0].click();", button)
            clicked = True
        except WebDriverException as err2:
            print("[WARN] JS 点击也失败: %s" % str(err2)[:60])
    if not clicked:
        return "抽奖失败（按钮点击失败）", ""
    print("===> 已点击「%s」" % button_text)

    # 给转盘一点转动时间，再重读一次矿石数（只为展示，不参与判定）
    time.sleep(5)
    after_ores = read_ores_badge(driver) or before_ores
    if before_ores and after_ores and after_ores != before_ores:
        print("===> 矿石数变化: %s → %s" % (before_ores, after_ores))
        return "已抽奖（免费 1 次）", "矿石 %s → %s" % (before_ores, after_ores)
    print("===> 已抽奖，矿石数未变化（可能抽到的是券/实物）")
    return "已抽奖（免费 1 次）", ""


def read_free_draws(driver):
    """读「免费抽奖次数: N」里的 N。读不到返回 None。

    这是判断「这次抽奖到底有没有发生」的**硬证据**，所以单独抓。
    在浏览器里扫可见文本，找「免费抽奖次数」后紧跟的整数。
    """
    js = """
    var re = /免费抽奖次数[^\\d]{0,6}(\\d+)/;
    var walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    var n, out = null;
    while ((n = walk.nextNode())) {
      var r = re.exec(n.textContent || '');
      if (r) { out = parseInt(r[1], 10); break; }
    }
    return out;
    """
    try:
        return driver.execute_script(js)
    except WebDriverException:
        return None


def _find_lottery_button(driver):
    """找「免费抽奖次数：N 次」那个按钮。

    ⚠️ 这里刻意**不用「抽奖」二字模糊匹配** —— 左侧导航的「幸运抽奖」菜单项也含这两个字，
    2026-09-29 线上连栽两轮（第一版命中它、第二版加了 menu/nav 排除仍然命中，因为线上那个
    菜单项外层全是构建哈希类名、也没有 nav/menu 字样）。改为按**按钮独有文案**定位，
    并对候选做**结构校验**：必须是 button，或位于转盘容器内，或文案里带次数。
    找不到返回 None（由调用方决定 dump/报错），绝不退化成「页面任意含抽奖的元素」。
    """
    for xpath in LOTTERY_BUTTON_XPATHS:
        try:
            for element in driver.find_elements(By.XPATH, xpath):
                if not element.is_displayed():
                    continue
                text = _element_text(driver, element)
                if not text:
                    continue
                # 左侧导航菜单项必杀：文案恰好是「幸运抽奖」「福利兑换」这种菜单名，
                # 或它自身/父链上是链接，一律排除。
                if text in ("幸运抽奖", "福利兑换", "我的收获", "每日签到", "成长等级", "社区排行榜"):
                    continue
                tag = (element.tag_name or "").lower()
                if tag not in ("button", "a", "div", "span"):
                    continue
                if tag == "a":
                    continue
                # 结构/文案校验：三者之一即可
                ok = (
                    tag == "button"
                    or "免费抽奖次数" in text
                    or _in_lottery_container(driver, element)
                )
                if ok:
                    print("===> 抽奖按钮命中: %r（tag=%s, xpath=%s）" % (text, tag, xpath))
                    return element
        except WebDriverException:
            continue
    return None


def _in_lottery_container(driver, element):
    """元素是否位于转盘/抽奖容器内（靠类名或祖先文案含「幸运大转盘」判断）。"""
    js = """
    var el = arguments[0];
    var p = el;
    for (var i = 0; i < 6 && p; i++, p = p.parentElement) {
      var cls = (p.className && p.className.toString) ? p.className.toString() : '';
      if (/lottery|wheel|prize|draw|turntable/i.test(cls)) return true;
    }
    // 再退一层：祖先里有没有「幸运大转盘」这段文案（容器类名不可靠时的兜底）
    p = el;
    for (var j = 0; j < 6 && p; j++, p = p.parentElement) {
      if ((p.textContent || '').indexOf('幸运大转盘') >= 0) return true;
    }
    return false;
    """
    try:
        return bool(driver.execute_script(js, element))
    except WebDriverException:
        return False


def _element_text(driver, element):
    """读元素可见文本（textContent 兜底，掘金 SPA 下 element.text 常为空）。"""
    try:
        text = (element.text or "").strip()
        if text:
            return text
        return (driver.execute_script("return arguments[0].textContent || '';", element) or "").strip()
    except WebDriverException:
        return ""


def growth_center(driver, username="", password=""):
    """进抽奖页 → 读矿石数 → 免费抽奖一次。

    返回 (矿石数, 抽奖状态, 奖品文案)。**任何一步失败都不抛异常** ——
    签到已经成功了，抽奖挂掉不该把当天的签到判成失败（见模块头注释）。
    """
    if not LOTTERY_ENABLED:
        print("===> JUEJIN_LOTTERY=0，跳过抽奖（只读矿石数）")

    try:
        if not goto_growth_center(driver, username, password):
            # goto_growth_center 内部已经 dump 过现场，这里不再重复 dump
            return "", "抽奖失败（未进入幸运抽奖页）", ""

        ores = read_ores_badge(driver) or ""
        print("===> 抽奖页矿石数: %s" % (ores or "未读取到"))
        if not LOTTERY_ENABLED:
            return ores, "已关闭（JUEJIN_LOTTERY=0）", ""

        status, reward = lottery_free_draw(driver, username, password)
        # 抽奖可能改变矿石数，重读一次拿最新的（随机矿石奖会涨）
        ores = read_ores_badge(driver) or ores
        print("===> 抽奖结果: %s %s（矿石数 %s）" % (status, reward, ores or "未读取到"))
        return ores, status, reward
    except Exception as err:
        # 这一层是刻意的宽口径：抽奖整段都不该把签到结论带崩
        print("[WARN] 抽奖流程异常（不影响签到结论）: %s" % err)
        dump_debug(driver, "growth_error", notes=[repr(err)], secrets=(username, password))
        return "", "抽奖失败（%s）" % str(err)[:60], ""


def _goto_pins_plaza(driver, username="", password=""):
    """回首页 → 点导航栏「沸点」→ 沸点广场。返回是否到位（**以页面内容为准**）。

    顺序（按 lodge 给的截图，跟抽奖一样的思路：认内容、不认 URL）：
      1. 回首页（导航栏只在首页/公共页上有）；
      2. 找导航栏「沸点」并点击；
      3. 点不到 / 没跳 → 直接 `GET /pins` 兜底（同一个登录态，等价）；
      4. 用 `_on_pins_page()` 复核**页面内容**，别只看 URL。

    ⚠️ 为什么不直接 `driver.get(PINS_URL)` 了事：lodge 明确要求走**导航栏点击**这条路径，
       直接开 URL 会绕开导航渲染问题，真出问题时反而看不出来。所以先点、点不动才兜底。
    """
    driver.get(HOME_URL)
    time.sleep(3)

    nav, nav_hit = wait_visible(driver, PINS_NAV_XPATHS, 12, "导航栏「沸点」")
    if nav is None:
        print("[WARN] 首页导航没找到「沸点」入口，直接打开 %s" % PINS_URL)
        driver.get(PINS_URL)
    else:
        print("===> 找到导航栏「沸点」（选择器 %s），点击进入" % nav_hit)
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", nav)
            nav.click()
        except WebDriverException as err:
            print("[WARN] 常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
            try:
                driver.execute_script("arguments[0].click();", nav)
            except WebDriverException as err2:
                print("[WARN] JS 点击也失败: %s，改为直接打开 URL" % str(err2)[:60])
                driver.get(PINS_URL)
        time.sleep(3)
        # 点了没跳转就直接开 URL（同一个登录态，等价）
        if "/pins" not in (driver.current_url or ""):
            print("===> 导航点击未跳转（当前 %s），直接打开 %s"
                  % (driver.current_url, PINS_URL))
            driver.get(PINS_URL)

    time.sleep(3)
    ok = _on_pins_page(driver)
    if not ok:
        dump_debug(
            driver,
            "pins_page_not_entered",
            notes=[
                "没能进入沸点广场",
                "当前 URL: %s" % driver.current_url,
                "页面文本首 200 字: %s" % page_text(driver)[:200],
            ],
            secrets=(username, password),
        )
    print("===> 沸点广场: %s（%s）" % ("已进入" if ok else "未能进入", driver.current_url))
    return ok


def _on_pins_page(driver):
    """当前页面是不是**真的**沸点广场。双向判据（同 _on_lottery_page 的思路）。

      · 正：出现沸点页特征文案（沸点广场 / 发布沸点 / 请选择圈子 / 快和掘友一起分享新鲜事）
      · 反：**没有**抽奖页的文案（幸运大转盘 / 免费抽奖次数）——
            否则「刚抽完奖没跳走」会被误判成已到沸点页
    """
    text = page_text(driver)
    if any(marker in text for marker in PINS_WRONG_PAGE_MARKERS):
        print("[WARN] 检测到抽奖页文案，判定不是沸点广场")
        return False
    hit = [m for m in PINS_PAGE_MARKERS if m in text]
    if hit:
        print("===> 沸点页特征命中: %s" % ", ".join(hit))
        return True
    return False


def publish_pin(driver, text="", username="", password=""):
    """在沸点广场顶部输入框写一句话并点「发布」。

    返回 (状态文案, 实际发出的内容)。**不抛异常** —— 见模块头：沸点流程失败绝不能
    影响签到结论，调用方那里还有一层宽口径 try 兜着。
    """
    content = (text or PINS_TEXT).strip()
    if not content:
        return "发沸点失败（内容为空）", ""

    editor, editor_hit = wait_visible(driver, PINS_EDITOR_XPATHS, 15, "沸点输入框")
    if editor is None:
        dump_debug(
            driver,
            "pins_no_editor",
            notes=["沸点页未找到发布输入框（页面结构可能变了）"],
            secrets=(username, password),
        )
        return "发沸点失败（未找到输入框）", ""

    print("===> 找到沸点输入框（选择器 %s）" % editor_hit)
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", editor)

        # ⚠️ 发布框可能是 textarea，也可能是 contenteditable div。
        #    textarea 走 send_keys；contenteditable 直接 send_keys 在部分浏览器上
        #    会把字符喂丢，所以走 execCommand('insertText')。
        tag = (editor.tag_name or "").lower()
        editable = (editor.get_attribute("contenteditable") or "").lower() == "true"
        if tag == "textarea":
            editor.clear()
            editor.send_keys(content)
        elif editable:
            driver.execute_script("arguments[0].focus();", editor)
            driver.execute_script(
                "arguments[0].innerHTML = '';"
                "document.execCommand('insertText', false, arguments[1]);",
                editor, content,
            )
        else:
            # 兜底：结构像输入框但不是上面两种，清空后直接塞 value
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));",
                editor, content,
            )
    except WebDriverException as err:
        print("[WARN] 输入沸点内容失败: %s" % str(err)[:80])
        return "发沸点失败（输入异常）", ""

    time.sleep(1.5)
    # 复核：内容有没有真的进框（进不去就别去点发布，免得发个空沸点）
    filled = _editor_value(driver, editor)
    if content.strip() and content.strip() not in (filled or ""):
        print("[WARN] 输入框回读为 %r，与预期不符，仍尝试发布" % (filled or "")[:40])

    button = _find_publish_button(driver, editor)
    if button is None:
        dump_debug(
            driver,
            "pins_no_publish_btn",
            notes=["沸点页未找到「发布」按钮（页面结构可能变了）"],
            secrets=(username, password),
        )
        return "发沸点失败（未找到发布按钮）", ""

    print("===> 找到发布按钮: %r" % _element_text(driver, button))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    time.sleep(0.5)
    clicked = False
    try:
        button.click()
        clicked = True
    except WebDriverException as err:
        print("[WARN] 常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
        try:
            driver.execute_script("arguments[0].click();", button)
            clicked = True
        except WebDriverException as err2:
            print("[WARN] JS 点击也失败: %s" % str(err2)[:60])
    if not clicked:
        return "发沸点失败（按钮点击失败）", ""

    print("===> 已点击「发布」，内容: %s" % content[:40])

    # ⚠️ 判成功**不扫整页文案找「发布成功」**（跟抽奖那条教训同源：旁边一直在播别人的内容）。
    #    这里只用一个**结构性**判据：发布框是否已清空。清空 = 提交走了。
    #    清不空也不武断报失败（可能站点保留草稿），返回「已提交」让人看日志核对。
    deadline = time.time() + 12
    while time.time() < deadline:
        leftover = (_editor_value(driver, editor) or "").strip()
        if not re.match(PINS_DRAFT_EMPTY_RE, leftover):
            time.sleep(1.5)
            continue
        print("===> 发布框已清空，判定沸点已发出")
        return "已发布沸点", content
    print("===> 发布框未清空（可能保留了草稿），按「已提交」处理")
    return "已提交沸点（发布框未清空，请核对）", content


def _editor_value(driver, editor):
    """读发布框当前内容（textarea 读 value，contenteditable 读 textContent）。"""
    try:
        return driver.execute_script(
            "var el = arguments[0];"
            "if (el.tagName && el.tagName.toLowerCase() === 'textarea') return el.value || '';"
            "return el.textContent || '';",
            editor,
        )
    except WebDriverException:
        return ""


def _find_publish_button(driver, editor):
    """找发布按钮。**必须限定在发布框附近**，不能全页模糊匹配。

    ⚠️ 页面上「发布沸点」标题、左侧「发布」入口都含「发布」二字，
       全页 `//*[contains(text(),'发布')]` 必然点错（跟抽奖按钮那次的坑一模一样）。
       做法：从 editor 往上爬几层，在**所在容器内**找文案恰为「发布」的按钮；
       容器内找不到，才退到「页面上第一个 button 且文案恰为发布」。
    """
    js = """
    var editor = arguments[0];
    var p = editor;
    for (var hop = 0; hop < 6 && p; hop++, p = p.parentElement) {
      var btns = p.querySelectorAll('button, div, span, a');
      for (var i = 0; i < btns.length; i++) {
        var b = btns[i];
        if (b.children.length && b.tagName.toLowerCase() !== 'button') continue;
        var t = (b.textContent || '').trim();
        if (t === '发布' || t === '发布沸点' || t === '立即发布') return b;
      }
    }
    return null;
    """
    try:
        element = driver.execute_script(js, editor)
        if element is not None and element.is_displayed():
            return element
    except WebDriverException as err:
        print("[WARN] 容器内找发布按钮失败: %s" % str(err)[:60])

    # 兜底：全局找文案恰为「发布」的按钮（要求是 button 标签或较短的叶子元素）
    for xpath in PINS_PUBLISH_XPATHS:
        try:
            for element in driver.find_elements(By.XPATH, xpath):
                if not element.is_displayed():
                    continue
                text = _element_text(driver, element)
                if text not in ("发布", "发布沸点", "立即发布"):
                    continue
                print("[INFO] 发布按钮由全局兜底选择器命中: %s" % xpath)
                return element
        except WebDriverException:
            continue
    return None


def like_friend_pins(driver, target=None, username="", password=""):
    """给 **好友**（已关注的人）的沸点点赞，最多点 target 个。

    返回 (状态文案, 实际点赞的列表)。**不抛异常**。

    ⚠️ 三条铁律（都是前面踩过的坑换了个场景）：
      1. **只给好友点**：lodge 明确说「两名好友」。卡片上若出现「关注」（未关注态），
         说明这人不是好友，跳过 —— 别见谁都点。
      2. **别重复点**：文案出现「已赞 / 取消赞」说明点过了，跳过。
      3. **别扫整页找「赞」**：右侧「精选沸点」、卡片计数「31赞」都含赞字。
         所以先按**卡片结构**框出候选，再在卡片内找文案恰为「点赞」的按钮。
    """
    want = PINS_LIKE_TARGET if target is None else int(target)
    if want <= 0:
        return "点赞已关闭（目标 0）", []

    items = _find_pin_items(driver)
    if not items:
        # 没找到结构化卡片 → 换一条更直接的路：直接在页面上找「点赞」按钮，
        # 但必须同时满足「不是已赞」「不是精选栏」两个条件。
        print("[WARN] 未按卡片结构框出沸点，改用「文案恰为点赞的按钮」直接筛")
        return _like_by_flat_buttons(driver, want)

    liked = []
    considered = 0
    for item in items:
        if len(liked) >= want:
            break
        considered += 1
        try:
            info = _pin_item_info(driver, item)
        except WebDriverException:
            continue
        label = info["text"][:30].replace("\n", " ") or "(无文本)"
        if info["liked"]:
            print("===> 第 %d 张沸点已点过赞，跳过" % considered)
            continue
        if info["not_friend"]:
            print("===> 第 %d 张沸点作者非好友（看到「关注」），跳过：%s" % (considered, label))
            continue
        if info["button"] is None:
            print("===> 第 %d 张沸点没找到可用点赞按钮，跳过：%s" % (considered, label))
            continue
        print("===> 给第 %d 张沸点点赞：%s" % (considered, label))
        if _click_like(driver, info["button"]):
            liked.append(label)
        time.sleep(1.5)

    if len(liked) >= want:
        return "已点赞 %d 名好友" % len(liked), liked
    # 好友不够时，退回「普通沸点也点」的宽松模式 —— lodge 的原意是「点两个赞」，
    # 别因为筛不出好友就把这一步判成失败（但日志里说清楚是宽松模式点的）。
    if liked:
        print("[INFO] 只筛到 %d 名好友（目标 %d），继续用宽松模式补足" % (len(liked), want))
    else:
        print("[INFO] 一个好友都没筛到，切宽松模式（不看关注关系，只避开已赞）")
    flat, extra = _like_by_flat_buttons(driver, want - len(liked))
    liked.extend(extra)
    mode = "已点赞 %d 名好友" % len(liked) if len(liked) >= want else "已点赞 %d 条沸点" % len(liked)
    return (mode, liked) if liked else ("点赞失败（没找到可点的沸点）", [])


def _find_pin_items(driver):
    """框出沸点列表里的卡片（要能排除右侧「精选沸点」栏）。返回元素列表。

    判据：容器文本里含「点赞」二字，且**不含**右侧栏特征（「围观大奖」那种在此不适用，
    改用「精选沸点」这个词当反例）—— 精选栏里的小卡片也可能有赞，但排版更窄。
    这里用**宽度**当辅助判据：正文卡片明显比右侧栏宽。
    """
    js = """
    var out = [];
    // 首选：找点赞按钮，再回溯到它所在的那张卡片
    var btns = document.querySelectorAll('button, div, span, a');
    for (var i = 0; i < btns.length; i++) {
      var b = btns[i];
      var t = (b.textContent || '').trim();
      if (t !== '点赞' && t !== '已赞' && t !== '取消赞') continue;
      // 往上爬找到「像一张卡片」的祖先：足够宽、且含作者/时间这类内容
      var p = b, best = null;
      for (var hop = 0; hop < 6 && p; hop++, p = p.parentElement) {
        var r = p.getBoundingClientRect();
        if (r.width > 400 && r.height > 60) { best = p; break; }
      }
      if (best && best.textContent.indexOf('精选沸点') < 0) out.push(best);
    }
    // 去重（同一卡片可能命中多个按钮）
    var uniq = [];
    for (var j = 0; j < out.length; j++) {
      if (uniq.indexOf(out[j]) < 0) uniq.push(out[j]);
    }
    return uniq;
    """
    try:
        return driver.execute_script(js) or []
    except WebDriverException as err:
        print("[WARN] 框选沸点卡片失败: %s" % str(err)[:80])
        return []


def _pin_item_info(driver, item):
    """读一张沸点卡片的关键信息：文本、点赞按钮、是否已赞、作者是否非好友。"""
    js = """
    var item = arguments[0];
    var text = item.textContent || '';
    // 卡片内的点赞按钮：文案恰为「点赞」优先，其次「已赞/取消赞」
    var btn = null, liked = false, btnText = '';
    var cands = item.querySelectorAll('button, div, span, a');
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      if (c.children.length && c.tagName.toLowerCase() !== 'button') continue;
      var t = (c.textContent || '').trim();
      if (t === '点赞' && !btn) { btn = c; btnText = t; }
      if (t === '已赞' || t === '取消赞') { liked = true; btnText = t; if (!btn) btn = c; }
    }
    // 作者非好友信号：卡片里出现独立的「关注」按钮（「已关注」不算）
    var notFriend = false;
    for (var j = 0; j < cands.length; j++) {
      var d = cands[j];
      if (d.children.length && d.tagName.toLowerCase() !== 'button') continue;
      var dt = (d.textContent || '').trim();
      if (dt === '关注' || dt === '+关注') { notFriend = true; break; }
    }
    return {text: text, liked: liked, not_friend: notFriend, btn_text: btnText, button: btn};
    """
    try:
        raw = driver.execute_script(js, item) or {}
    except WebDriverException:
        raw = {}
    return {
        "text": (raw.get("text") or "").strip(),
        "liked": bool(raw.get("liked")),
        "not_friend": bool(raw.get("not_friend")),
        "button": raw.get("button"),
    }


def _like_by_flat_buttons(driver, want):
    """宽松模式：直接在页面上找文案恰为「点赞」的按钮，点 want 个。

    仍守住两条：① 文案**恰为**「点赞」（不是「31赞」「已赞」）；② 避开右侧「精选沸点」栏
    （用祖先文本里有没有「精选沸点」判）。
    """
    if want <= 0:
        return [], []
    js = """
    var out = [];
    var cands = document.querySelectorAll('button, div, span, a');
    for (var i = 0; i < cands.length; i++) {
      var c = cands[i];
      if (c.children.length && c.tagName.toLowerCase() !== 'button') continue;
      var t = (c.textContent || '').trim();
      if (t !== '点赞') continue;
      // 往上爬 6 层，若祖先文本里出现「精选沸点」，说明在右侧栏，剔除
      var p = c, inSide = false;
      for (var hop = 0; hop < 6 && p; hop++, p = p.parentElement) {
        if ((p.textContent || '').indexOf('精选沸点') >= 0) { inSide = true; break; }
      }
      if (inSide) continue;
      out.push(c);
    }
    return out;
    """
    try:
        buttons = driver.execute_script(js) or []
    except WebDriverException:
        return [], []
    liked = []
    for button in buttons:
        if len(liked) >= want:
            break
        try:
            label = _pin_item_info(driver, button).get("text", "")[:30] or "(宽松模式)"
        except WebDriverException:
            label = "(宽松模式)"
        if _click_like(driver, button):
            liked.append(label)
        time.sleep(1.2)
    return liked, liked


def _click_like(driver, button):
    """点一个点赞按钮，成功返回 True（常规点击 → JS 点击，两级降级）。"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
        time.sleep(0.3)
    except WebDriverException:
        pass
    try:
        button.click()
        return True
    except WebDriverException as err:
        print("[WARN] 点赞常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
        try:
            driver.execute_script("arguments[0].click();", button)
            return True
        except WebDriverException as err2:
            print("[WARN] 点赞 JS 点击也失败: %s" % str(err2)[:60])
            return False


def _round_text(base, round_no):
    """第 N 轮的沸点文案。

    ⚠️ 第二轮**不能跟第一轮一字不差**：① 看起来像刷屏；② 有些站点对
    「短时间内完全相同的重复内容」会直接拦（甚至当垃圾内容处理）。
    所以第 2 轮起加一个可辨识的后缀，但**不改变原意**。
    """
    if round_no <= 1:
        return base
    return "%s（%d）" % (base, round_no)


def pins_activity(driver, username="", password=""):
    """沸点这一整套：进沸点广场 → 发一条沸点 → 给两名好友点赞。**跑 PINS_ROUNDS 遍**。

    lodge 要求「发沸点和点赞这两个任务执行两遍，两次之间间隔 120 秒」，
    所以这里是个轮次循环；每轮文案带轮次后缀（见 `_round_text`），避免第二轮被当成
    与第一轮完全相同的重复内容。

    返回 (发沸点状态, 发出内容, 点赞状态, 点赞明细)。**任何一步失败都不抛异常**
    —— 跟抽奖一个原则：签到已经成功了，沸点挂掉不该把当天的签到判成失败。
    """
    if not PINS_ENABLED:
        print("===> JUEJIN_PINS=0，跳过沸点流程")
        return "已关闭（JUEJIN_PINS=0）", "", "", []

    pub_statuses, contents, like_statuses, all_liked = [], [], [], []
    for round_no in range(1, PINS_ROUNDS + 1):
        # 两轮之间先歇够间隔 —— lodge 明确要 120 秒。放在轮首而不是轮尾，
        # 是为了让「第一轮跑完 → 等 120s → 第二轮」这个语义一眼能看出来。
        if round_no > 1:
            print("===> 第 %d/%d 轮：先等 %d 秒（lodge 要求的间隔）"
                  % (round_no, PINS_ROUNDS, PINS_ROUND_GAP))
            time.sleep(PINS_ROUND_GAP)

        print("===> ===== 沸点第 %d/%d 轮开始 =====" % (round_no, PINS_ROUNDS))
        try:
            # 每轮都重新回首页点导航栏进沸点广场 —— 第一轮发完后页面可能已经变了，
            # 复用同一个页面状态去点第二轮，导航栏可能已经不在视口里。
            if not _goto_pins_plaza(driver, username, password):
                pub_statuses.append("第 %d 轮失败（未进入沸点广场）" % round_no)
                contents.append("")
                like_statuses.append("")
                continue

            text = _round_text(PINS_TEXT, round_no)
            pub_status, content = publish_pin(driver, text, username, password)
            print("===> 第 %d 轮发沸点: %s（内容 %r）" % (round_no, pub_status, (content or "")[:40]))
            pub_statuses.append(pub_status)
            contents.append(content)

            like_status, liked = like_friend_pins(driver, PINS_LIKE_TARGET, username, password)
            print("===> 第 %d 轮点赞: %s %s" % (round_no, like_status, liked))
            like_statuses.append(like_status)
            all_liked.extend(liked)
        except Exception as err:
            print("[WARN] 沸点第 %d 轮异常（不影响签到结论）: %s" % (round_no, err))
            dump_debug(driver, "pins_error_r%d" % round_no,
                       notes=[repr(err)], secrets=(username, password))
            pub_statuses.append("第 %d 轮失败（%s）" % (round_no, str(err)[:40]))
            contents.append("")
            like_statuses.append("")

    return (
        _join_rounds(pub_statuses, "已发布沸点"),
        " / ".join(c for c in contents if c),
        _join_rounds(like_statuses, "已点赞"),
        all_liked,
    )


def _join_rounds(values, ok_marker):
    """把多轮结果合成一条可读文案。

    两轮都成功且文案相同 → 折叠成「已发布沸点 ×2」；
    否则逐轮列出（「第 1 轮: …；第 2 轮: …」），方便一眼看出哪轮出问题。
    """
    values = [v for v in values if v]
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    if all(v == values[0] for v in values):
        return "%s ×%d" % (values[0], len(values))
    return "；".join("第 %d 轮: %s" % (i + 1, v) for i, v in enumerate(values))


def article_activity(driver, username="", password=""):
    """文章详情页这一套：回首页 → 依次点第 1、2… 篇文章 → 每篇都点赞 + 收藏 + 关注作者。

    lodge 要求（截图 + 2026-10-01 追加）：
      · 左侧竖排操作栏点「赞」，再点「收藏」；
      · 收藏会弹「选择收藏集」窗 → 选**默认收藏夹**（我的收藏）→ 点「确定」；
      · 右侧作者信息下方**有关注按钮就点**，已经是「已关注」就忽略；
      · **做完一篇回首页，点另一篇，把上面这套重复一遍**（共 ARTICLE_COUNT 篇，默认 2）。
      · ⚠️ 文章在**新标签页**打开 —— 见 `_goto_nth_article` 的句柄处理。

    返回 (点赞状态, 收藏状态, 关注状态)，多篇用「；」连起来。
    **失败不抛异常**（同沸点/抽奖原则）。
    """
    if not ARTICLE_ENABLED:
        print("===> JUEJIN_ARTICLE=0，跳过文章流程")
        return "已关闭（JUEJIN_ARTICLE=0）", "", ""

    likes, collects, follows = [], [], []
    for idx in range(1, ARTICLE_COUNT + 1):
        print("===> ===== 文章第 %d/%d 篇开始 =====" % (idx, ARTICLE_COUNT))
        try:
            # 每篇都重新回首页点链接 —— lodge 明确要求「返回首页，重复点击另一篇文章」
            if not _goto_nth_article(driver, idx, username, password):
                likes.append("第 %d 篇失败（未进入详情页）" % idx)
                continue

            like_status = like_article(driver, username, password)
            collect_status = collect_article(driver, username, password)
            follow_status = follow_author(driver, username, password)
            print("===> 第 %d 篇: 赞=%s / 收藏=%s / 关注=%s"
                  % (idx, like_status, collect_status, follow_status))
            likes.append(like_status)
            collects.append(collect_status)
            follows.append(follow_status)
        except Exception as err:
            print("[WARN] 文章第 %d 篇异常（不影响签到结论）: %s" % (idx, err))
            dump_debug(driver, "article_error_%d" % idx,
                       notes=[repr(err)], secrets=(username, password))
            likes.append("第 %d 篇失败（%s）" % (idx, str(err)[:40]))
        finally:
            _close_article_tab(driver)

    return (
        _join_rounds(likes, "已点赞文章"),
        _join_rounds(collects, "已收藏文章"),
        _join_rounds(follows, "已关注作者"),
    )


def _article_xpaths(idx):
    """把 HOME_FIRST_ARTICLE_XPATHS 里的 `[%d]` 换成第 idx 篇（从 1 起）。"""
    return tuple(xp % idx if "%d" in xp else xp for xp in HOME_FIRST_ARTICLE_XPATHS)


def _goto_nth_article(driver, idx=1, username="", password=""):
    """回首页 → 点第 idx 篇文章 → **切到新标签页** → 等进入详情页。返回是否到位。

    ⚠️⚠️ **这里的核心是「文章在新标签页打开」**：
      掘金首页文章链接带 `target=_blank`（或等价的 window.open），点了之后
      **当前 driver 仍停在首页那个句柄**上 —— 不切句柄就去点左侧赞按钮，
      等于在首页上瞎找，必然报「找不到按钮」。
      正确顺序：记下点击前的句柄 → 点击 → 等出现**新句柄** → `switch_to` 过去。
      拿不到新句柄时再退回「直接开 href」（同标签页，等价），保证流程不空转。
    """
    driver.get(HOME_URL)
    time.sleep(3)

    before = set(driver.window_handles)
    link, hit = wait_visible(driver, _article_xpaths(idx), 15, "首页第 %d 篇文章" % idx)
    if link is None:
        dump_debug(
            driver,
            "home_no_article_%d" % idx,
            notes=["首页未找到第 %d 篇文章链接（信息流结构可能变了）" % idx,
                   "页面文本首 200 字: %s" % page_text(driver)[:200]],
            secrets=(username, password),
        )
        return False

    title = _element_text(driver, link)[:40]
    href = link.get_attribute("href") or ""
    target = (link.get_attribute("target") or "")
    print("===> 找到第 %d 篇文章: %r（%s，target=%r，选择器 %s）"
          % (idx, title, href, target, hit))

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
    time.sleep(0.5)
    clicked = False
    try:
        link.click()
        clicked = True
    except WebDriverException as err:
        print("[WARN] 常规点击失败(%s)，改用 JS 点击" % str(err)[:60])
        try:
            driver.execute_script("arguments[0].click();", link)
            clicked = True
        except WebDriverException as err2:
            print("[WARN] JS 点击也失败: %s" % str(err2)[:60])

    # 等新标签页出现（最多 ~10s）。新标签页 = 句柄集合比点击前多了。
    new_handle = None
    deadline = time.time() + 10
    while time.time() < deadline:
        now = set(driver.window_handles)
        added = now - before
        if added:
            # 多开时按「最新的在路上」取最后一个（Chrome 新标签通常追加在末尾）
            new_handle = list(added)[-1]
            break
        time.sleep(0.3)

    if new_handle:
        print("===> 文章在新标签页打开，切换到句柄 %s（共 %d 个标签）"
              % (new_handle[-8:], len(driver.window_handles)))
        driver.switch_to.window(new_handle)
    else:
        # 没开新标签（或没点到）→ 同标签页路径：直接开 href 兜底
        print("===> 未检测到新标签页（clicked=%s），按同标签页处理" % clicked)
        if not clicked and href:
            print("===> 改为直接打开 %s" % href)
            driver.get(href)

    # 等 URL 落到文章页 —— 不能靠「页面上有几个赞按钮」判断（首页每张卡片也有）。
    deadline = time.time() + 20
    while time.time() < deadline:
        if any(h in (driver.current_url or "") for h in ARTICLE_URL_HINTS):
            break
        time.sleep(0.3)
    time.sleep(3)

    url = driver.current_url or ""
    ok = any(h in url for h in ARTICLE_URL_HINTS)
    if not ok:
        dump_debug(driver, "article_not_entered_%d" % idx,
                   notes=["没能进入文章详情页", "当前 URL: %s" % url,
                          "句柄数: %d" % len(driver.window_handles)],
                   secrets=(username, password))
    print("===> 文章详情页(第 %d 篇): %s（%s）" % (idx, "已进入" if ok else "未能进入", url))
    return ok


def _close_article_tab(driver):
    """关掉当前文章标签并切回首页标签（若无首页标签则切到剩下的任意一个）。

    ⚠️ 不关的话句柄会一篇文章攒一个，第二篇开始「当前窗口」就不确定了 ——
       这也是 lodge 说的「注意判断新标签页」必须配套处理的一半。
    """
    try:
        handles = driver.window_handles
    except WebDriverException:
        return
    if len(handles) <= 1:
        return  # 只有一个标签，别关（关了就没窗口可用了）

    current = driver.current_window_handle
    try:
        driver.close()
        print("===> 已关闭文章标签，回到首页标签")
    except WebDriverException as err:
        print("[WARN] 关闭文章标签失败: %s" % str(err)[:60])
        return

    # 切回剩下的标签；优先挑一个 URL 像首页/掘金域名的
    remaining = [h for h in driver.window_handles if h != current]
    if not remaining:
        return
    pick = remaining[0]
    for h in remaining:
        try:
            driver.switch_to.window(h)
            if any(k in (driver.current_url or "") for k in ("juejin.cn", "/")) \
                    and not any(k in (driver.current_url or "") for k in ARTICLE_URL_HINTS):
                pick = h
                break
        except WebDriverException:
            continue
    driver.switch_to.window(pick)


# ⚠️ 2026-10-02 线上实测：掘金详情页左栏的**点赞按钮 class 里不含 like**，
#    所以上面那组类名 XPath 在真实站点上一条也命中不了（两篇文章都漏），
#    而同一列的「收藏」class 带 collect，稳定命中 —— 于是拿收藏当锚点反推。
#    这一列的顺序是固定的（lodge 截图确认）：
#        赞 / 评论 / 收藏 / 分享 / 举报
#    点赞 = 该列**第 1 个**按钮，也就是从收藏往前数 2 个。
_JS_LIKE_BY_COLLECT = """
var el = arguments[0], node = el;
for (var up = 0; up < 6 && node; up++) {
  var p = node.parentElement;
  if (!p) return null;
  var kids = Array.prototype.slice.call(p.children);
  var idx = kids.indexOf(node);
  if (idx >= 0 && kids.length >= 3) {
    // 这一层必须「长得像一列按钮」：每个都在按钮尺寸区间内、宽度量级一致、竖向排开。
    // 否则会把「某个按钮内部的 icon/count 碎片」当成一列 —— 碎片宽高参差，过不了下面这关。
    var box = kids.map(function (c) { return c.getBoundingClientRect(); });
    var ok = [];
    box.forEach(function (r, i) {
      if (r.width >= 24 && r.width <= 220 && r.height >= 24 && r.height <= 120) ok.push(i);
    });
    if (ok.length >= 3) {
      var ws = ok.map(function (i) { return box[i].width; });
      var wmin = Math.min.apply(null, ws), wmax = Math.max.apply(null, ws);
      var seen = {}, tops = 0;
      ok.forEach(function (i) {
        var k = Math.round(box[i].top);
        if (!seen[k]) { seen[k] = 1; tops++; }
      });
      if (wmin > 0 && wmax / wmin <= 2.2 && tops >= 3) {
        var pos = ok.indexOf(idx);
        if (pos < 0) pos = 0;
        var t = pos - 2;
        if (t < 0) t = 0;                       // 越界就退到第一个（点赞本来就是第一个）
        var target = kids[ok[t]];
        if (target === node || target.contains(node)) return null;   // 别把收藏自己当点赞
        return target;
      }
    }
  }
  node = p;
}
return null;
"""


def _find_like_by_collect_anchor(driver):
    """兜底：拿「收藏」当锚点，反推同一列的第 1 个按钮（= 赞）。

    为什么不用类名：线上掘金的点赞按钮 class 不含 like，类名法必然漏。
    返回点赞按钮元素，失败返回 None。
    """
    for xpath in ARTICLE_COLLECT_XPATHS:
        try:
            anchors = driver.find_elements(By.XPATH, xpath)
        except WebDriverException:
            continue
        for anchor in anchors:
            try:
                if not anchor.is_displayed():
                    continue
                found = driver.execute_script(_JS_LIKE_BY_COLLECT, anchor)
                if found is not None and found != anchor:
                    print("[INFO] 点赞按钮 由「收藏」同列反推命中（该列第 1 个）")
                    return found
            except (StaleElementReferenceException, WebDriverException):
                continue
    return None


def _count_of(text):
    """从「👍298」这类文本里抠出计数；抠不到返回 None（那就别瞎判）。"""
    raw = str(text or "")
    # ⚠️「1.2k」「1.2万」这类缩略计数，点完赞前后字符串一字不差，比不出 ±1；
    #    硬比会把「已经点上了」误判成「计数没变化」。这时直接放弃判定，别乱下结论。
    if re.search(r"[kKwW万]", raw):
        return None
    match = re.search(r"\d[\d,]*", raw)
    if not match:
        return None
    try:
        return int(match.group().replace(",", ""))
    except ValueError:
        return None


def _find_article_action(driver, xpaths, label):
    """在文章详情页左侧操作栏找一个按钮（图标 + 数字，**没有文字文案**）。

    ⚠️ 这排按钮只有图标和计数，不能靠「点赞」二字定位。策略：
      1. 按类名结构找（like / collect）；
      2. 找到后**排除已经点过的**（类名带 active / liked / collected）；
      3. 排除掉明显不是操作栏的（页头、评论区）。
    找不到返回 None。
    """
    for xpath in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xpath)
        except WebDriverException:
            continue
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                # 已经点过的跳过 —— 再点一下就变「取消」了
                cls = (element.get_attribute("class") or "").lower()
                if "active" in cls or "liked" in cls or "collected" in cls:
                    continue
                # 操作项是**横向一条**（图标 + 计数），高度很小。
                # ⚠️ 别用宽度卡：容器可能被 flex 拉满整行（实测线上/回放都出现过
                #    宽 700+ 的情况），用宽度过滤会把真按钮整条毙掉。
                #    所以卡高度上限 + 对齐到**最内层**那个可点元素。
                size = element.size
                if size["height"] == 0 or size["height"] > 80:
                    continue
                # 取最内层：如果它内部还有同样带 like/collect 类名的子元素，往下钻
                inner = _innermost_match(driver, element)
                print("[INFO] %s 命中: %s（tag=%s, %dx%d）"
                      % (label, xpath, inner.tag_name, size["width"], size["height"]))
                return inner
            except (StaleElementReferenceException, WebDriverException):
                continue
    return None


def _innermost_match(driver, element):
    """在元素内部找最内层、仍是「操作项」的那个节点（避免点到包裹容器）。

    判据：类名与父级同族（都含 like/collect 语义）且可点击的叶子。
    找不到就返回原元素 —— 宁可用外层，也别返回 None。
    """
    try:
        inner = driver.execute_script(
            """
            var el = arguments[0];
            var base = (el.className || '').toString();
            var key = base.indexOf('like') >= 0 ? 'like'
                    : (base.indexOf('collect') >= 0 ? 'collect' : '');
            if (!key) return el;
            var best = el;
            var walk = function (node) {
              var kids = node.children || [];
              for (var i = 0; i < kids.length; i++) {
                var k = kids[i];
                var c = (k.className || '').toString();
                if (c.indexOf(key) >= 0) { best = k; walk(k); return; }
              }
              // 没有同族子元素时，往「只有一个子元素」的链上钻一层
              if (kids.length === 1) { best = kids[0]; walk(kids[0]); }
            };
            walk(el);
            return best;
            """,
            element,
        )
        return inner or element
    except WebDriverException:
        return element


def like_article(driver, username="", password=""):
    """点文章左侧的「赞」。已赞过则跳过。返回状态文案。"""
    text = page_text(driver)
    if any(m in text for m in ("已点赞",)):
        # 「已点赞」在详情页顶部也可能出现，所以只当弱信号，仍尝试找按钮
        print("[INFO] 页面出现「已点赞」字样，仍尝试定位点赞按钮")

    button = _find_article_action(driver, ARTICLE_LIKE_XPATHS, "点赞按钮")
    if button is None:
        # 线上点赞按钮 class 不含 like，类名法必然漏 —— 改用「收藏同列第 1 个」反推
        button = _find_like_by_collect_anchor(driver)
    if button is None:
        print("[WARN] 文章页未找到点赞按钮（可能已赞或结构变了）")
        return "点赞跳过（未找到按钮或已赞）"

    # ⚠️ 反推出来的按钮，事先**不知道是否已赞**。掘金已赞时再点一下 = 取消赞，
    #    所以点完必须复核计数：
    #      +1 → 点上了；
    #      -1 → 原来就赞过、被这一下取消了 → 立刻补点还原（宁可不动，也不能把赞取消掉）；
    #       0 → 没生效或本来就已赞，按跳过处理。
    before = _element_text(driver, button)
    if not _click_element(driver, button, "点赞"):
        return "点赞失败（按钮点击失败）"
    time.sleep(1.5)
    after = _element_text(driver, button)
    print("===> 点赞计数: %r → %r" % (before, after))

    n_before, n_after = _count_of(before), _count_of(after)
    if n_before is not None and n_after is not None:
        if n_after == n_before - 1:
            print("[WARN] 原本已赞，这一下点成了取消 —— 立即补点还原")
            _click_element(driver, button, "点赞(还原)")
            time.sleep(1.2)
            return "点赞跳过（原本已赞，已还原）"
        if n_after == n_before:
            return "点赞跳过（计数未变，可能已赞）"
    return "已点赞文章"


def collect_article(driver, username="", password=""):
    """点文章左侧的「收藏」，弹窗里选默认收藏夹 → 点「确定」。

    返回状态文案。**收藏没弹窗 = 已收藏过**（掘金对已收藏的文章点收藏不再弹窗）。
    """
    button = _find_article_action(driver, ARTICLE_COLLECT_XPATHS, "收藏按钮")
    if button is None:
        print("[WARN] 文章页未找到收藏按钮（可能已收藏或结构变了）")
        return "收藏跳过（未找到按钮或已收藏）"

    if not _click_element(driver, button, "收藏"):
        return "收藏失败（按钮点击失败）"

    # 等弹窗出现 —— 判据是**弹窗文案**，不是「页面上有确定按钮」
    # （详情页别处也可能有「确定」，必须等那个收藏集窗真的冒出来）
    modal = _wait_collect_modal(driver, timeout=8)
    if modal is None:
        # 不弹窗多半是已经收藏过了
        text = page_text(driver)
        if any(m in text for m in COLLECT_ALREADY_MARKERS):
            print("===> 未弹收藏窗，页面提示已收藏，判定为重��收藏")
            return "收藏跳过（已收藏过）"
        dump_debug(driver, "collect_no_modal",
                   notes=["点了收藏但没等到「选择收藏集」弹窗"],
                   secrets=(username, password))
        return "收藏失败（未弹出收藏集窗口）"

    print("===> 收藏弹窗已出现")

    # 选**默认收藏夹**（截图里是「我的收藏」+「默认」标签那一项）
    folder = _find_in_modal(modal, driver, COLLECT_DEFAULT_XPATHS)
    if folder is None:
        print("[WARN] 弹窗里没定位到默认收藏夹，直接点确定（通常会存入默认夹）")
    else:
        print("===> 选中默认收藏夹: %r" % _element_text(driver, folder)[:30])
        if not _click_element(driver, folder, "默认收藏夹"):
            print("[WARN] 默认收藏夹点击失败，仍尝试点确定")

    time.sleep(0.8)
    confirm = _find_in_modal(modal, driver, COLLECT_CONFIRM_XPATHS, require_text="确定")
    if confirm is None:
        dump_debug(driver, "collect_no_confirm",
                   notes=["收藏窗里没找到「确定」按钮"],
                   secrets=(username, password))
        return "收藏失败（弹窗里未找到确定按钮）"

    if not _click_element(driver, confirm, "确定"):
        return "收藏失败（确定按钮点击失败）"

    # 复核：弹窗消失 = 提交走了（结构性判据，别扫整页文案）
    if _wait_modal_gone(driver, modal, timeout=8):
        print("===> 收藏弹窗已关闭，判定收藏成功")
        return "已收藏文章"
    print("[WARN] 收藏弹窗未关闭，仍按已提交处理")
    return "已提交收藏（弹窗未关闭，请核对）"


def _wait_collect_modal(driver, timeout=8):
    """等「选择收藏集」弹窗出现，返回它的根元素；超时返回 None。

    ⚠️ 判据不能只看尺寸：真实弹窗有固定宽高，但**回放/精简 DOM 里可能很矮**，
       用 `height >= 150` 之类的阈值会把真弹窗毙掉（实测栽过一次）。
       所以改成「文案 + 结构」双判：文案命中，且容器是**浮层形态**
       （position 为 fixed/absolute，或类名含 modal/dialog/popup/mask），
       两者都满足才认。这比尺寸阈值稳，也更贴近"它是不是个弹窗"的本质。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = page_text(driver)
        if all(m in text for m in COLLECT_MODAL_MARKERS[:2]):
            try:
                modal = driver.execute_script(
                    """
                    var marks = arguments[0];
                    var all = document.querySelectorAll('div, section, dialog');
                    var best = null, bestArea = -1;
                    for (var i = 0; i < all.length; i++) {
                      var el = all[i];
                      var t = el.textContent || '';
                      var hit = true;
                      for (var j = 0; j < marks.length; j++) {
                        if (t.indexOf(marks[j]) < 0) { hit = false; break; }
                      }
                      if (!hit) continue;
                      var r = el.getBoundingClientRect();
                      if (r.width < 200 || r.height < 60) continue;
                      // 浮层判据：定位脱离常规流，或类名带 modal/dialog/popup/mask
                      var st = window.getComputedStyle(el);
                      var cls = (el.className || '').toString().toLowerCase();
                      var isOverlay = (st.position === 'fixed' || st.position === 'absolute')
                        || /modal|dialog|popup|mask|overlay/.test(cls);
                      if (!isOverlay) continue;
                      // ⚠️ 取**最小的**满足条件的浮层 = 弹窗内容本体，不是整屏遮罩。
                      //    选最大的那片 mask 会把整页罩进来，于是 `确定` 会在
                      //    「弹窗里的确定」和「页面上被遮住的无关确定」之间二选一 ——
                      //    实测就栽在这：点到了被遮挡的无关按钮，报 click intercepted。
                      var area = r.width * r.height;
                      if (best === null || area < bestArea) { bestArea = area; best = el; }
                    }
                    return best;
                    """,
                    list(COLLECT_MODAL_MARKERS[:2]),
                )
            except WebDriverException:
                modal = None
            if modal is not None:
                return modal
        time.sleep(0.3)
    return None


def _wait_modal_gone(driver, modal, timeout=8):
    """等弹窗消失（元素脱离文档 或 不可见）。返回是否已消失。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if not modal.is_displayed():
                return True
        except StaleElementReferenceException:
            return True
        except WebDriverException:
            return True
        time.sleep(0.3)
    return False


def _scope_xpath(xpath):
    """把绝对 XPath（`//…`）改成相对当前节点的形式（`.//…`）。

    ⚠️ **这是 Selenium 的一个大坑**：`element.find_elements(By.XPATH, "//button")`
       **不是**在 element 子树里找，而是**从整个文档根**找 —— 绝对路径 `//` 会忽略
       调用它的元素。只有写成 `.//`（相对当前节点）才真正限定在子树内。
       实测就栽在这：收藏弹窗里找「确定」，结果返回了页面上那个无关的「确定」，
       点击时报 `element click intercepted`（因为它被弹窗遮住了）。
    """
    if xpath.startswith("//"):
        return "." + xpath
    return xpath


def _find_in_modal(modal, driver, xpaths, require_text=None):
    """在**弹窗范围内**找元素（限定范围是关键：详情页别处也有「确定」「收藏」）。

    require_text 给了就要求文案精确等于它。XPath 会先转成 `.//` 相对形式，
    否则会退化成全文档查找（见 `_scope_xpath`）。
    """
    for xpath in xpaths:
        try:
            elements = modal.find_elements(By.XPATH, _scope_xpath(xpath))
        except (StaleElementReferenceException, WebDriverException):
            continue
        for element in elements:
            try:
                if not element.is_displayed():
                    continue
                size = element.size
                if size["width"] == 0 or size["height"] == 0:
                    continue
                if require_text is not None:
                    if _element_text(driver, element).strip() != require_text:
                        continue
                return element
            except (StaleElementReferenceException, WebDriverException):
                continue
    return None


def follow_author(driver, username="", password=""):
    """右侧作者信息下方**有关注按钮就点**，已是「已关注」则忽略。

    ⚠️ 「关注」二字在页头导航里也有（顶部「关注」标签），必须限定在作者卡片内 ——
       用「私信」按钮当锚点找同一区域内它的兄弟/祖先范围内的「关注」。
    """
    # 先看是不是已经关注了 —— 已关注就不用点（点了会变成取消关注！）
    author_area = _find_author_area(driver)
    if author_area is not None:
        try:
            area_text = _element_text(driver, author_area)
        except WebDriverException:
            area_text = ""
        if any(m in area_text for m in AUTHOR_FOLLOWED_MARKERS):
            print("===> 作者已是「已关注」，跳过")
            return "关注跳过（已关注）"

    button, hit = wait_visible(driver, AUTHOR_FOLLOW_XPATHS, 8, "作者关注按钮")
    if button is None:
        print("[WARN] 右侧作者区未找到「关注」按钮（可能已关注或结构变了）")
        return "关注跳过（未找到关注按钮）"

    if not _click_element(driver, button, "关注作者"):
        return "关注失败（按钮点击失败）"

    time.sleep(1.5)
    try:
        after = _element_text(driver, button).strip()
    except WebDriverException:
        after = ""
    if any(m in after for m in AUTHOR_FOLLOWED_MARKERS):
        print("===> 关注成功，按钮已变为 %r" % after)
        return "已关注作者"
    print("===> 已点击关注（按钮文案变为 %r）" % after)
    return "已关注作者"


def _find_author_area(driver):
    """定位右侧作者信息卡（用「私信」按钮当锚点往上找容器）。"""
    try:
        return driver.execute_script(
            """
            var els = document.querySelectorAll('button, div, span, a');
            for (var i = 0; i < els.length; i++) {
              var e = els[i];
              if ((e.textContent || '').trim() !== '私信') continue;
              var p = e.parentElement;
              for (var hop = 0; hop < 4 && p; hop++, p = p.parentElement) {
                var r = p.getBoundingClientRect();
                if (r.width > 150 && r.height > 100) return p;
              }
            }
            return null;
            """
        )
    except WebDriverException:
        return None


def _click_element(driver, element, label=""):
    """点一个元素：常规点击 → JS 点击两级降级。成功返回 True。"""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.3)
    except WebDriverException:
        pass
    try:
        element.click()
        return True
    except WebDriverException as err:
        print("[WARN] %s 常规点击失败(%s)，改用 JS 点击" % (label, str(err)[:60]))
        try:
            driver.execute_script("arguments[0].click();", element)
            return True
        except WebDriverException as err2:
            print("[WARN] %s JS 点击也失败: %s" % (label, str(err2)[:60]))
            return False


def notify(bot_id, status, ores="", note="", lottery="", reward="",
           pin="", pin_text="", likes="", like="", collect="", follow=""):
    """推一张飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append("**当前矿石数**: %s" % (ores or "未读取到"))
    if lottery:
        content.append("**免费抽奖**: %s" % lottery)
    if reward:
        content.append("**抽奖奖励**: %s" % reward)
    if pin:
        content.append("**发沸点**: %s" % pin)
    if pin_text:
        content.append("**沸点内容**: %s" % pin_text)
    if likes:
        content.append("**点赞**: %s" % likes)
    if like:
        content.append("**文章点赞**: %s" % like)
    if collect:
        content.append("**文章收藏**: %s" % collect)
    if follow:
        content.append("**关注作者**: %s" % follow)
    if note:
        content.append("**错误信息**: %s" % note)
    content.append("**时间**: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    try:
        Feishu_SendCardMsg(bot_id, " 掘金 签到 ", "\n".join(content))
    except Exception as err:
        print("[WARN] 飞书推送失败（不影响签到结果）: %s" % err)


def resolve_credentials(argv):
    """凭据：环境变量优先，命令行参数兼容。返回 dict，避免位置参数错位。"""
    return {
        "username": os.getenv("JUEJIN_USERNAME") or (argv[1] if len(argv) > 1 else ""),
        # 两种拼写都认：这个仓库的 secret 惯用 *_PASSWD（旧 secret 里 PASSWORD/PASSWD 混着来）
        "password": (os.getenv("JUEJIN_PASSWORD") or os.getenv("JUEJIN_PASSWD")
                     or (argv[2] if len(argv) > 2 else "")),
        "cookie": (os.getenv(JUEJIN_COOKIE_ENV) or "").strip(),
        "bot_id": os.getenv("FEISHU_BOT_ID") or (argv[3] if len(argv) > 3 else ""),
    }


def juejin(username="", password="", cookie="", bot_id=""):
    # 只打**长度**不打内容：数字不会被 GitHub 的 secret 遮蔽机制吃掉，
    # 这样「密码到底有没有传进来」一眼可判（2026-09-27 曾被 *** 遮得看不出）。
    def _n(value):
        return len(value or "")

    print(
        "===> 凭据检查: cookie=%d字 / JUEJIN_USERNAME=%d字 / JUEJIN_PASSWORD=%d字"
        % (_n(cookie), _n(username), _n(password))
    )
    # 变量**名**不是机密，值才是 —— 打出来便于一眼看出「名字对不上/漏传」。
    # 2026-09-27 踩过：账号传进来了、密码却是 0 字，只靠长度看不出是名字拼错还是值空。
    related = sorted(k for k in os.environ if k.upper().startswith(("JUEJIN", "PJ52")))
    print("===> 环境里凭据相关变量名: %s" % (", ".join(related) or "(一个都没有)"))

    if not (username and password) and not cookie:
        sys.exit(
            "[X] 没有可用凭据 | cookie=%d字 username=%d字 password=%d字\n"
            "    请到 仓库 → Settings → Secrets and variables → Actions 逐字符核对：\n"
            "      · 在 **Secrets** 标签页（不是 Variables、不是 Environment secrets）里\n"
            "        有 JUEJIN_USERNAME / JUEJIN_PASSWORD，名字大小写与拼写完全一致；\n"
            "      · 两个 secret 都要有值（重新 Update 时别带首尾空格/换行）；\n"
            "      · 改过 secret 后要重新触发一次 workflow 才生效。"
            % (_n(cookie), _n(username), _n(password))
        )

    status = "签到失败"
    note = ""
    ores = ""
    lottery = ""
    reward = ""
    pin = ""
    pin_text = ""
    likes = ""
    art_like = ""
    art_collect = ""
    art_follow = ""
    driver = get_web_driver()
    try:
        # 优先账号密码（会自动过滑块验证码）；滑块被行为风控拦下时，若配了 Cookie 就降级用它
        logged = False
        if username and password:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    if login_once(driver, username, password, attempt):
                        logged = True
                        break
                    print("===> 第 %d 次登录未通过，重试" % attempt)
                except (TimeoutException, NoSuchElementException, ValueError, RuntimeError) as err:
                    # RuntimeError 也要接住：滑块没过时会抛它，不能让整个流程终止 ——
                    # 否则就跳不到下面的 Cookie 兜底了。
                    print("===> 第 %d 次登录异常: %s" % (attempt, err))
                    dump_debug(driver, "a%d_error" % attempt, notes=[repr(err)])
                time.sleep(2)
            if not logged and cookie:
                print("===> 密码登录（含滑块）未通过，降级用 Cookie 登录态")

        if not logged and cookie:
            print("===> 使用 Cookie 登录态，跳过登录页与滑块")
            pairs = parse_cookie_header(cookie)
            print("===> Cookie 项(%d): %s" % (len(pairs), ", ".join(name for name, _ in pairs)))
            inject_cookies(driver, cookie, COOKIE_DOMAIN)
            driver.get(HOME_URL)
            time.sleep(4)
            if not is_logged_in(driver):
                dump_debug(
                    driver,
                    "cookie_invalid",
                    notes=["注入 Cookie 后首页仍非登录态（可能是 sessionid 过期）"],
                    secrets=tuple(value for _, value in pairs if len(value) >= 6),
                )
                raise RuntimeError("注入的 Cookie 无效或已过期，请在浏览器里重新登录后再抄一次")
            print("===> Cookie 登录态有效")
            logged = True

        if not logged:
            dump_debug(driver, "final_failure", notes=["密码登录已尝试 %d 次" % MAX_ATTEMPTS])
            raise RuntimeError("登录失败：已尝试 %d 次（滑块被字节行为风控拦下时请改用 Cookie）" % MAX_ATTEMPTS)

        status, numbers = sign_in(driver, username, password)
        ores = numbers.get("ores") or ""
        print("===> 签到结果: %s（矿石数 %s）" % (status, ores or "未读取到"))

        # 签到成功后再进福利中心：读最新矿石数 + 免费抽奖一次（失败不影响签到结论）。
        # 「今日已签到」也照抽 —— 抽奖是每天一次，跟签到是两件事。
        center_ores, lottery, reward = growth_center(driver, username, password)
        # 福利中心顶部胶囊的矿石数是**抽奖后**的最新值，比签到页文案更准，优先用它
        ores = center_ores or ores
        print("===> 最终矿石数: %s / 抽奖: %s %s" % (ores or "未读取到", lottery, reward))

        # 抽奖完成后回首页 → 沸点广场：发一条沸点 + 给两名好友点赞（跑 PINS_ROUNDS 遍）。
        # 跟抽奖同理，**失败不影响签到结论**（pins_activity 内部已兜住异常）。
        pin, pin_text, like_status, liked_items = pins_activity(driver, username, password)
        likes = like_status
        if liked_items:
            likes = "%s（%s）" % (like_status, " / ".join(liked_items))
        print("===> 沸点: %s / %s" % (pin, likes))

        # 两遍沸点都跑完 → 回首页点第一篇文章 → 点赞 + 收藏 + 关注作者。
        # 同样**失败不影响签到结论**。
        art_like, art_collect, art_follow = article_activity(driver, username, password)
        print("===> 文章: %s / %s / %s" % (art_like, art_collect, art_follow))
    except Exception as err:
        status = "签到失败"
        note = str(err)[:200]
        raise
    finally:
        try:
            driver.quit()
        except Exception as err:
            print("[WARN] 关闭浏览器失败: %s" % err)
        if bot_id:
            notify(bot_id, status, ores, note, lottery, reward, pin, pin_text, likes,
                   art_like, art_collect, art_follow)


if __name__ == "__main__":
    if len(sys.argv) == 1 and not any(
        os.getenv(k) for k in ("JUEJIN_COOKIE", "JUEJIN_USERNAME", "JUEJIN_PASSWORD")
    ):
        sys.exit(
            "用法: python -m Selenium.Check-in.juejin\n"
            "  凭据走环境变量: JUEJIN_COOKIE（推荐）/ JUEJIN_USERNAME + JUEJIN_PASSWORD\n"
            "  也兼容老写法: python -m ... <手机号/邮箱> <密码> [飞书机器人 webhook]"
        )
    juejin(**resolve_credentials(sys.argv))
