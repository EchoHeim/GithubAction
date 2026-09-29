# -*- coding: UTF-8 -*-
"""掘金抽奖回归测试 —— 合成 DOM，不连掘金、不需要凭据。

⚠️ 为什么值得留着：2026-09-29 线上**两轮全错**，而且错的都是「看起来对」的地方：
  第 1 轮：进错页面（/growth 是「成长等级」页，没有转盘）+ 签到页读数串位 + 点错按钮
  第 2 轮：还是进错页面（该点左侧菜单「幸运抽奖」），而且矿石数读到了等级阈值 25000

假页面刻意还原真实结构（按 lodge 的两张截图）：
  1. 签到页三个统计卡：数字在上、标签在下（`4/连续签到天数` `5/累计签到天数` `55174/当前矿石数`）
  2. 签到页左侧菜单含「幸运抽奖」（点了才到转盘页）—— 这正是抽奖的正确入口
  3. 转盘页顶部矿石胶囊、转盘、`免费抽奖次数：1 次` 按钮
  4. 「围观大奖」栏播报**别人**的中奖（不能当自己的战利品）
  5. 「成长等级」页作为反例：有 `JY8 25000` 这类数字，且没有转盘
  6. 转盘页**页头挂 4 位角标**（`消息 1234` / `未读 5678`）—— 专门压「最上方大数字抢答」这个洞
     （第 5 轮线上矿石数读成 `2026` 就是页面杂数字抢答，同源问题）

覆盖 11 项断言：T0 签到页读数 / T1 进抽奖页 / T2 成长等级页不得判为抽奖页 /
T3 不得把 25000 当矿石数 / T4 页头 4 位角标不得抢答矿石胶囊 / T5 免费次数 /
T6 按钮命中（不误点左侧菜单）/ T7 围观大奖数字不得污染矿石数 /
T8 抽奖动作（点完即返回，不判结果）/ T9 抽后矿石更新 / T10 二次抽奖跳过

跑法（**必须先清代理**，否则 chromedriver 报 unhandled request）：
    env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \\
        python -B Selenium/Check-in/juejin_regress_test.py

只测判据与选择器，不发飞书、不碰真实账号。
"""
import http.server
import importlib.util
import os
import socketserver
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from selenium import webdriver  # noqa: E402

PORT = 8937

# 左侧菜单（签到页与转盘页共用，类名是哈希、不含 menu/nav/item）
NAV = """
<aside class="s1"><div class="a1"><a class="c3" href="/user/center/signin">每日签到</a></div>
<div class="a1"><a class="c3" href="#">社区排行榜</a></div>
<div class="a1"><a class="c3" href="#">成长等级</a></div>
<div class="a1"><a class="c3" id="navLottery" href="/user/center/lottery">幸运抽奖</a></div>
<div class="a1"><a class="c3" href="#">福利兑换</a></div>
<div class="a1"><a class="c3" href="#">我的收获</a></div></aside>
"""

# 签到页：三个独立统计卡，**数字在前、标签在后**（照抄截图 1）
PAGE_SIGNIN = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>每日签到 - 掘金</title></head>
<body>
<header><div class="h1"><img class="avatar" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></div></header>
""" + NAV + """
<div class="main"><h1>每日签到</h1>
  <div class="stat-card"><div class="num">4</div><div class="lbl">连续签到天数</div></div>
  <div class="stat-card"><div class="num">5</div><div class="lbl">累计签到天数</div></div>
  <div class="stat-card"><div class="num">55174</div><div class="lbl">当前矿石数</div></div>
  <div class="day">29 Sept. 2026</div>
  <button class="signin-btn">今日已签到</button>
</div>
<script>
document.getElementById('navLottery').addEventListener('click', function (e) {
  e.preventDefault(); location.href = '/user/center/lottery';
});
</script>
</body></html>""")

# 转盘页（真正要进的页面）
#   ⚠️ 刻意在 header 里塞一个「消息角标 1234」：4 位数、且在**最上方**、比矿石胶囊还靠上。
#      这是 `read_ores_badge` 主路径（取页面最上方大数字）最容易翻车的地方 ——
#      2 位数角标会被 `len>=4` 顺手挡掉，4 位数才会真正抢答。
#      第 5 轮线上读到 2026 就属同类问题（页面杂数字抢答），T4 专职守这个洞。
PAGE_LOTTERY = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>幸运抽奖 - 掘金</title></head>
<body>
<header><div class="nav-badge">1234</div><div class="msg-count">5678</div></header>
""" + NAV + """
<div class="main">
  <h1>掘金福利限量抽</h1>
  <div class="top-bar"><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="矿石">
    <div class="cap"><span class="capnum">55174</span></div></div>
  <div class="t">幸运大转盘</div>
  <div class="wheel-box">
    <div class="prize">随机矿石</div>
    <!-- 陷阱：围观大奖 —— 别人的中奖播报，绝不能算自己的 -->
    <div class="k1"><div class="m1">围观大奖</div>
      <div class="o1">恭喜 胡毛毛 抽中 Pico Neo3</div>
      <div class="o1">恭喜 cv大法... 抽中 苹果耳机AIRPOD</div>
    </div>
    <button class="free-btn" id="drawBtn">免费抽奖次数：1 次</button>
    <button class="ten-btn">十连抽 2000</button>
  </div>
</div>
<script>
document.getElementById('drawBtn').addEventListener('click', function () {
  setTimeout(function () {
    document.querySelector('.capnum').textContent = '55184';
    this.textContent = '今日已抽完';
    var m = document.createElement('div');
    m.className = 'modal-mask';
    m.innerHTML = '<div class="modal"><p>恭喜你抽中随机矿石 10 个</p>'
                + '<button class="ok">开心收下</button></div>';
    m.querySelector('.ok').addEventListener('click', function () { m.remove(); });
    document.body.appendChild(m);
  }.bind(this), 600);
});
</script>
</body></html>""")

# 反例页：成长等级（第 1 轮误入的就是它）—— 有 25000 这种数字，但没有转盘
PAGE_GROWTH_WRONG = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>成长等级 - 掘金</title></head>
<body>
""" + NAV + """
<div class="main"><h1>成长等级</h1><div class="t1">掘友分明细</div>
<div class="lv"><span>0</span> JY1 <span>15</span> JY2 <span>25000</span> JY8</div>
<div class="r">等级规则 等级权益 升级行为 今日掘友分 0</div></div>
</body></html>""")


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path
        if "lottery" in path:
            body = PAGE_LOTTERY
        elif "growth" in path:
            body = PAGE_GROWTH_WRONG
        else:
            body = PAGE_SIGNIN
        raw = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


def main():
    srv = socketserver.TCPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % PORT

    spec = importlib.util.spec_from_file_location("jj", os.path.join(HERE, "juejin.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.SIGNIN_URL = base + "/user/center/signin"
    m.LOTTERY_URL = base + "/user/center/lottery"
    m.GROWTH_URL = base + "/user/center/growth"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("window-size=1440x900")
    options.page_load_strategy = "none"
    driver = webdriver.Chrome(options=options)

    fails = []
    try:
        # T0：签到页三个统计卡读数（数字在前、标签在后）
        driver.get(m.SIGNIN_URL)
        time.sleep(1.5)
        nums = m.read_numbers(driver)
        print("[T0] 签到页读数: %s (期望 矿石=55174 / 连续=4 / 累计=5)" % nums)
        if nums["ores"] != "55174":
            fails.append("T0 矿石数应为 55174，实得 %r" % nums["ores"])
        if nums["streak"] != "4":
            fails.append("T0 连续应为 4，实得 %r" % nums["streak"])
        if nums["total"] != "5":
            fails.append("T0 累计应为 5，实得 %r" % nums["total"])

        # T1：从签到页左侧菜单点「幸运抽奖」应进入转盘页（正确入口）
        ok = m.goto_growth_center(driver)
        print("[T1] 进抽奖页: %s (%s)" % (ok, driver.current_url))
        if not ok:
            fails.append("T1 没能进入抽奖页，URL=%s" % driver.current_url)
        if "lottery" not in driver.current_url:
            fails.append("T1 URL 应为 lottery，实得 %s" % driver.current_url)

        # T2：反例页必须被判为「不是抽奖页」（第 1 轮就死在这）
        driver.get(m.GROWTH_URL)
        time.sleep(1.0)
        wrong = m._on_lottery_page(driver)
        print("[T2] 「成长等级」页被判定为抽奖页: %s (期望 False)" % wrong)
        if wrong:
            fails.append("T2 把「成长等级」页误判成抽奖页")

        # T3：成长等级页上的 25000 绝不能被当成矿石数（第 2 轮就是这数字）
        ores_wrong = m.read_ores_badge(driver)
        print("[T3] 成长等级页读到的矿石数: %r (期望非 '25000')" % ores_wrong)
        if ores_wrong == "25000":
            fails.append("T3 又把等级阈值 25000 当矿石数了")

        # T4：转盘页读矿石胶囊
        #    ⚠️ 页面顶部挂了「消息角标 1234」和「未读 5678」，都是 4 位数、都在最上方、
        #      都比矿石胶囊靠上。读出来必须是 55174 —— 一旦读到 1234/5678，
        #      说明主路径（取页面最上方大数字）被页头杂数字抢答了。
        driver.get(m.LOTTERY_URL)
        time.sleep(1.5)
        ores = m.read_ores_badge(driver)
        print("[T4] 矿石胶囊: %r (期望 '55174'，不得被页头角标 1234/5678 抢答)" % ores)
        if ores != "55174":
            fails.append("T4 矿石胶囊应为 55174，实得 %r" % ores)

        # T5：免费次数
        free = m.read_free_draws(driver)
        print("[T5] 免费次数: %r (期望 1)" % free)
        if free != 1:
            fails.append("T5 免费次数应为 1，实得 %r" % free)

        # T6：按钮定位必须命中真按钮，不能是左侧菜单「幸运抽奖」
        btn = m._find_lottery_button(driver)
        btn_text = m._element_text(driver, btn) if btn else None
        print("[T6] 命中按钮: %r (期望 '免费抽奖次数：1 次')" % btn_text)
        if btn_text != "免费抽奖次数：1 次":
            fails.append("T6 按钮定位错误，实得 %r" % btn_text)

        # T7：未抽奖时不得把「围观大奖」里的数字当矿石数
        #    （第 5 轮线上读成 2026 就是被「© 2026 稀土掘金」这类页面杂数字坑的，
        #     这里用「围观大奖」栏兜同一个洞：旁人的中奖数字不能污染矿石数判据）
        pre_ores = m.read_ores_badge(driver)
        print("[T7] 未抽奖时的矿石数: %r (期望 '55174'，不得是围观大奖里的数字)" % pre_ores)
        if pre_ores != "55174":
            fails.append("T7 未抽奖时矿石数应为 55174，实得 %r" % pre_ores)

        # T8：抽奖动作本身（第 5 轮起**不再判结果**，点完即返回「已抽奖」）
        status, reward = m.lottery_free_draw(driver)
        print("[T8] 抽奖: status=%r reward=%r" % (status, reward))
        if status != "已抽奖（免费 1 次）":
            fails.append("T8 应为「已抽奖（免费 1 次）」，实得 %r" % status)

        # T9：抽后矿石数更新
        ores2 = m.read_ores_badge(driver)
        print("[T9] 抽后矿石: %r (期望 '55184')" % ores2)
        if ores2 != "55184":
            fails.append("T9 抽后矿石应为 55184，实得 %r" % ores2)

        # T10：二次抽奖必须跳过
        status2, _ = m.lottery_free_draw(driver)
        print("[T10] 二次抽奖: %r (期望 今日已抽完（跳过）)" % status2)
        if "已抽完" not in status2:
            fails.append("T10 二次抽奖应跳过，实得 %r" % status2)
    finally:
        driver.quit()
        srv.shutdown()

    print("\n==== 结果 ====")
    for f in fails:
        print("[FAIL] " + f)
    print("全部通过" if not fails else "有 %d 项失败" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
