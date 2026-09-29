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

回归测试：`python -B Selenium/Check-in/juejin_regress_test.py`（合成 DOM，11 项断言）。
改选择器后务必重跑；跑之前要清代理（见 LOCAL_RUN.md）。

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


def notify(bot_id, status, ores="", note="", lottery="", reward=""):
    """推一张飞书卡片。推送失败只告警，绝不因此把签到判成失败。"""
    content = ["**签到状态**: %s" % status]
    content.append("**当前矿石数**: %s" % (ores or "未读取到"))
    if lottery:
        content.append("**免费抽奖**: %s" % lottery)
    if reward:
        content.append("**抽奖奖励**: %s" % reward)
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
            notify(bot_id, status, ores, note, lottery, reward)


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
