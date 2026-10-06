# -*- coding: UTF-8 -*-
"""掘金抽奖回归测试 —— 合成 DOM，不连掘金、不需要凭据。

⚠️ 为什么值得留着：2026-09-29 线上**两轮全错**，而且错的都是「看起来对」的地方：
  第 1 轮：进错页面（/growth 是「成长等级」页，没有转盘）+ 签到页读数串位 + 点错按钮
  第 2 轮：还是进错页面（该点左侧菜单「幸运抽奖」），而且矿石数读到了等级阈值 25000

假页面刻意还原真实结构（按 lodge 的截图）：
  1. 签到页三个统计卡：数字在上、标签在下（`4/连续签到天数` `5/累计签到天数` `55174/当前矿石数`）
  2. 签到页左侧菜单含「幸运抽奖」（点了才到转盘页）—— 这正是抽奖的正确入口
  3. 转盘页顶部矿石胶囊、转盘、`免费抽奖次数：1 次` 按钮
  4. 「围观大奖」栏播报**别人**的中奖（不能当自己的战利品）
  5. 「成长等级」页作为反例：有 `JY8 25000` 这类数字，且没有转盘
  6. 转盘页**页头挂 4 位角标**（`消息 1234` / `未读 5678`）—— 专门压「最上方大数字抢答」这个洞
     （第 5 轮线上矿石数读成 `2026` 就是页面杂数字抢答，同源问题）
  7. 首页顶部导航栏（**沸点入口是个没有 href 的 `<span>`**，走 JS 路由）—— 2026-10-01 新增
  8. 沸点广场：发布框 + 发布按钮 + 4 张卡片（好友A / 好友B / 非好友带「关注」/ 已赞过）
     + 右侧「精选沸点」栏也放「点赞」按钮当陷阱 + 卡片里的「31赞」计数当陷阱

覆盖断言：T0 签到页读数 / T1 进抽奖页 / T2 成长等级页不得判为抽奖页 /
T3 不得把 25000 当矿石数 / T4 页头 4 位角标不得抢答矿石胶囊 / T5 免费次数 /
T6 按钮命中（不误点左侧菜单）/ T7 围观大奖数字不得污染矿石数 /
T8 抽奖动作（点完即返回，不判结果）/ T9 抽后矿石更新 / T10 二次抽奖跳过 /
T11 进沸点广场 / T12 抽奖页不得判为沸点页 / T13 发沸点 / T14 发布后框清空 /
T15 新沸点上榜 / T16 点赞两名好友（跳过非好友与已赞）/ T17 点赞生效 /
T18 精选栏不得被误点 / T19 二次点赞幂等 /
T20 轮次文案不同 / T21 多轮结果折叠 / T22 沸点跑两遍 /
T23 进第 1 篇（**新标签页要切句柄**）/ T24 文章点赞（**无类名，靠收藏同列反推**）/
T24b 已赞再点**不得取消**（反推的按钮不知是否已赞，靠计数复核自愈）/
T25 收藏走弹窗默认夹+确定 / T26 关注作者 / T27 已关注幂等 /
T28 关标签回首页 / T29 第 2 篇重复一遍 / T30 article_activity 端到端 2 篇 /
T31 XPath 序号替换

跑法（脚本内已自动绕开 localhost 代理，一般直接跑即可）：
    python -B Selenium/CheckIN/juejin_regress_test.py
    # 万一仍报 unhandled request，说明代理把 localhost 也接管了，手工兜底：
    # env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \\
    #     python -B Selenium/CheckIN/juejin_regress_test.py

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
from Selenium.base import _bypass_proxy_for_localhost  # noqa: E402

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

# 首页：**必须有顶部导航栏**（lodge 要求「回首页 → 点导航栏的沸点」）。
#   ⚠️ 导航项的形态刻意还原真实站点：**不是 `<a href>`，而是一个 `<span>` 走 JS 路由** ——
#      线上掘金导航就是构建过的 SPA，很多项压根没有 href，
#      只认 `//a[@href='/pins']` 会全部落空（T11 曾因此退化成直接开 URL）。
PAGE_HOME = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>掘金 - 一个帮助开发者成长的社区</title></head>
<body>
<header><nav class="n1">
  <a class="c3" href="/">首页</a>
  <span class="c3" id="navPins">沸点</span>
  <a class="c3" href="/course">课程</a>
  <a class="c3" href="/user/center/signin">签到</a>
</nav></header>
<div class="main"><h1>推荐</h1><div class="feed">
  <!-- ⚠️ 文章链接刻意带 target="_blank"：掘金首页就是这么开的，
       回归测试要验的正是「新标签页要切句柄」这条（不切就会在首页上瞎找按钮）。 -->
  <div class="entry"><a class="title" target="_blank" href="/post/7100000000000000001">外包前端和大厂前端，写的代码到底有什么本质区别？</a>
    <div class="meta">ErpanOmer · 3.1k阅读 · 38赞</div></div>
  <div class="entry"><a class="title" target="_blank" href="/post/7100000000000000002">亿级订单表分库分表设计，从 0 到 1 全流程</a>
    <div class="meta">吃橘子得干活 · 619阅读 · 14赞</div></div>
  <div class="entry"><a class="title" target="_blank" href="/post/7100000000000000003">用 WorkBuddy / Codex + Obsidian 搭建自生长的个人知识库实战</a>
    <div class="meta">苍何 · 2.7k阅读</div></div>
</div></div>
<script>
document.getElementById('navPins').addEventListener('click', function () {
  location.href = '/pins';
});
</script>
</body></html>""")

# ── 文章详情页（2026-10-01 新增，第二版改为按 id 生成）──
# 按 lodge 截图还原，埋的坑：
#   1. 左侧竖排操作栏的「赞 / 收藏」**只有图标 + 数字，没有文字文案**
#      —— 只能靠类名结构定位，靠文案必落空；
#   2. 点收藏弹「选择收藏集」窗：默认收藏夹是「我的收藏」+「默认」标签，右下角「确定」；
#      ⚠️ 详情页别处也放了个「确定」按钮（比如某个无关表单）—— 不限定在弹窗内必然点错；
#   3. 右侧作者卡：有关注按钮（蓝色实心「关注」）+「私信」并排；
#      ⚠️ 页头导航也有「关注」标签，全页模糊匹配会点错。
# ⚠️ 第二版改成**按文章 id 生成**：每篇文章的赞/收藏/关注状态各自独立，
#    这样「第二篇重复一遍」才能验出「它确实对另一篇又做了一遍」，
#    而不是在同一个页面上把第一遍的状态又读了一遍。
def page_article(article_id="7100000000000000001", like_count=38, collect_count=28,
                 follow_text="关注", title="外包前端和大厂前端，写的代码到底有什么本质区别？"):
    return ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>%s - 掘金</title>
<style>
/* 左侧竖排操作栏：真实掘金是 48x48 的按钮列。
   ⚠️ 必须先给尺寸：div 默认 block 会拉满整行，那么「按按钮尺寸识别这一列」的反推法就失效了。 */
.article-layout { display:flex; align-items:flex-start; gap:16px; }
.action-bar { display:flex; flex-direction:column; width:48px; flex:0 0 48px; }
.act-item { width:48px; height:48px; display:flex; flex-direction:column;
            align-items:center; justify-content:center; cursor:pointer; }
</style></head>
<body data-article-id="%s">
<header><nav class="n1">
  <a class="c3" href="/">首页</a><a class="c3" href="/pins">沸点</a>
  <a class="c3" href="/follow">关注</a>
</nav></header>
<div class="article-layout">
  <div class="action-bar">
    <!-- ⚠️ 刻意**不写 like 类名**：线上掘金点赞按钮的 class 就不含 like（2026-10-02 实测），
         夹具里写 like-btn 会让测试「假过」——测试绿了，线上一个都找不到。 -->
    <div class="act-item" id="artLike"><span class="icon">👍</span><span class="cnt">%d</span></div>
    <div class="act-item comment-btn"><span class="icon">💬</span><span class="cnt">19</span></div>
    <div class="act-item collect-btn" id="artCollect"><span class="icon">★</span><span class="cnt">%d</span></div>
    <div class="act-item share-btn"><span class="icon">↗</span></div>
  </div>
  <div class="article-body">
    <h1>%s</h1>
    <div class="art-meta">ErpanOmer 2026-08-25 · 3,145 阅读 8分钟</div>
    <p>先说一个可能会得罪人的事实 😅。</p>
  </div>
  <aside class="author-card" id="authorCard">
    <div class="aname">ErpanOmer</div>
    <div class="stats"><span>238 文章</span><span>1.8m 阅读</span><span>2.9k 粉丝</span></div>
    <div class="btns"><button class="follow-btn" id="followBtn">%s</button>
      <button class="dm-btn">私信</button></div>
  </aside>
  <!-- 陷阱：详情页别处也有个「确定」，收藏窗没限定范围就会点到它 -->
  <div class="unrelated-form"><button class="ok-btn" id="otherOk">确定</button></div>
</div>
<!-- 收藏弹窗（初始隐藏）。
     ⚠️ 刻意用 position:fixed 做成**真浮层**（真实站点就是 fixed 遮罩）：
        回归测试要验的正是「靠浮层定位、而不是靠尺寸阈值」这条判据。 -->
<div class="modal-mask" id="collectMask" style="display:none;position:fixed;inset:0;">
  <div class="collect-modal" style="position:absolute;">
    <div class="m-title">选择收藏集</div>
    <div class="m-sub">选择或创建你想添加的收藏集</div>
    <div class="folder-item" id="folderDefault">
      <span class="fname">我的收藏</span><span class="tag">默认</span>
      <span class="fmeta">2篇文章 · 0订阅</span>
    </div>
    <div class="m-foot"><span class="new-folder">＋新建收藏集</span>
      <button class="confirm-btn" id="confirmBtn">确定</button></div>
  </div>
</div>
<script>
var liked = false, collected = false, followed = %s, savedFolder = null;
window.__artState = function () {
  return {liked: liked, collected: collected, followed: followed, savedFolder: savedFolder,
          likeCount: document.getElementById('artLike').querySelector('.cnt').textContent,
          collectCount: document.getElementById('artCollect').querySelector('.cnt').textContent};
};
// 点赞是 **toggle**：已赞时再点会取消（计数 -1）。真实掘金就是这个行为，
// 夹具照实模拟，才能验出脚本「点完复核计数、误取消自动还原」这段自愈逻辑。
document.getElementById('artLike').addEventListener('click', function () {
  liked = !liked;
  this.className = 'act-item' + (liked ? ' active' : '');
  var c = this.querySelector('.cnt');
  c.textContent = String(parseInt(c.textContent, 10) + (liked ? 1 : -1));
});
document.getElementById('artCollect').addEventListener('click', function () {
  if (collected) return;
  document.getElementById('collectMask').style.display = 'block';
});
document.getElementById('folderDefault').addEventListener('click', function () {
  document.querySelectorAll('.folder-item').forEach(function (f) {
    f.className = f.className.replace(' selected', '');
  });
  this.className += ' selected';
});
document.getElementById('confirmBtn').addEventListener('click', function () {
  var sel = document.querySelector('.folder-item.selected');
  savedFolder = sel ? sel.querySelector('.fname').textContent : '我的收藏';
  collected = true;
  document.getElementById('collectMask').style.display = 'none';
  var c = document.getElementById('artCollect').querySelector('.cnt');
  c.textContent = String(parseInt(c.textContent, 10) + 1);
  document.getElementById('artCollect').className = 'act-item collect-btn collected';
});
document.getElementById('followBtn').addEventListener('click', function () {
  if (followed) return;
  followed = true;
  this.textContent = '已关注';
  this.className = 'follow-btn followed';
});
</script>
</body></html>""" % (title, article_id, like_count, collect_count, title, follow_text,
                     "true" if follow_text == "已关注" else "false"))


# 兼容旧引用：默认那篇（第一篇）
PAGE_ARTICLE = page_article()

# ── 沸点广场（2026-10-01 新增）──
# 按 lodge 截图还原，专门埋了这几个坑：
#   1. 顶部导航栏「沸点」入口（要点击进入，且**没有 href**，走 JS 路由）；
#   2. 发布框 placeholder 很长（只认开头那截）+ 右下角「发布」按钮；
#   3. 列表里三张卡片：① 好友A（已关注、未赞）② 好友B（已关注、未赞）③ 非好友（有「关注」按钮）
#      —— 必须只点①②，跳过③；
#   4. 还有一张**已经点过赞**的好友卡片（文案「已赞」）—— 必须跳过不重复点；
#   5. 右侧「精选沸点」栏里也放一个「点赞」按钮 —— 绝不能点到它；
#   6. 卡片里放「31赞」这类**计数文案** —— 模糊匹配「赞」字会误命中，必须只认「点赞」。
PAGE_PINS = ("""<!DOCTYPE html><html><head><meta charset="utf-8"><title>沸点 - 掘金</title></head>
<body>
<header><nav class="n1">
  <a class="c3" href="/">首页</a>
  <span class="c3" id="navPins">沸点</span>
  <a class="c3" href="/course">课程</a>
</nav></header>
<aside class="s2"><div class="a2"><a class="c3" href="#">社区排行榜</a></div>
<div class="a2"><a class="c3" href="#">沸点广场</a></div></aside>
<div class="main">
  <div class="publish-box" id="pubBox">
    <textarea id="pinEditor" placeholder="快和掘友一起分享新鲜事！告诉你个小秘密，发布沸点时添加圈子和话题会被更多掘友看到哦~"></textarea>
    <button id="pubBtn">发布</button>
  </div>
  <div class="pin-list">
    <div class="pin-item" id="item1">
      <div class="author">喜马拉雅9527</div><div class="time">21分钟前</div>
      <div class="content">你觉得你是在干正事，其实你可以在玩。当然，玩也是正事。</div>
      <div class="acts"><span class="act">分享</span><span class="act">评论</span>
        <span class="count">31赞</span><span class="like-btn">点赞</span></div>
    </div>
    <div class="pin-item" id="item2">
      <div class="author">科技热点</div><div class="time">41分钟前</div>
      <div class="content">#每日快讯# 「宁王」座下，车企的三次大撤退</div>
      <div class="acts"><span class="act">分享</span><span class="act">评论</span>
        <span class="count">12赞</span><span class="like-btn">点赞</span></div>
    </div>
    <div class="pin-item" id="item3">
      <div class="author">路人甲</div><div class="time">1小时前</div>
      <div class="content">这条不是我好友发的，不能点。</div>
      <div class="acts"><span class="act">分享</span><span class="act">评论</span>
        <span class="count">5赞</span><span class="follow-btn">关注</span>
        <span class="like-btn">点赞</span></div>
    </div>
    <div class="pin-item" id="item4">
      <div class="author">已经赞过的好友</div><div class="time">2小时前</div>
      <div class="content">这条我之前已经点过赞了，别重复点。</div>
      <div class="acts"><span class="act">分享</span><span class="act">评论</span>
        <span class="like-btn liked">已赞</span></div>
    </div>
  </div>
  <aside class="side-picks">
    <div class="side-title">精选沸点</div>
    <div class="side-item">家里人说母亲已经冷倒大腿了…<span class="like-btn">点赞</span></div>
    <div class="side-item">掘下希望的每一杆…<span class="like-btn">点赞</span></div>
  </aside>
</div>
<script>
document.getElementById('navPins').addEventListener('click', function () {
  location.href = '/pins';
});
document.getElementById('pubBtn').addEventListener('click', function () {
  var ed = document.getElementById('pinEditor');
  if (!(ed.value || '').trim()) return;
  var post = document.createElement('div');
  post.className = 'pin-item mine';
  post.innerHTML = '<div class="author">MacLodge</div><div class="time">刚刚</div>'
    + '<div class="content">' + ed.value + '</div>'
    + '<div class="acts"><span class="act">分享</span><span class="act">评论</span>'
    + '<span class="like-btn">点赞</span></div>';
  document.querySelector('.pin-list').insertBefore(post, document.querySelector('.pin-list').firstChild);
  ed.value = '';
});
// 点赞按钮：点一下文案转「已赞」——回归测试靠这个变化判断「点赞是否真的生效」。
// ⚠️ 用**事件委托**而不是逐个 addEventListener：发沸点后新插入的那张卡片是运行时
//    创建的，逐个绑定时它还不存在，会导致「点了没反应」，T17 会误判成功能坏了。
document.addEventListener('click', function (e) {
  var b = e.target.closest ? e.target.closest('.like-btn') : null;
  if (!b) return;
  if ((b.textContent || '').trim() !== '点赞') return;
  b.textContent = '已赞';
  b.className = 'like-btn liked';
});
</script>
</body></html>""")


class Handler(http.server.BaseHTTPRequestHandler):
    # ⚠️ 路由**必须按路径段精确匹配**，不能用 `in` 子串判断 ——
    #    `/user/center/signin` 里也含 "pins"，首页请求会被误派成签到页，
    #    于是「导航栏点沸点」那条断言（T11）永远走不到真正的首页。
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/pins"):
            body = PAGE_PINS
        elif path.endswith("/lottery"):
            body = PAGE_LOTTERY
        elif path.endswith("/growth"):
            body = PAGE_GROWTH_WRONG
        elif path.endswith("/signin"):
            body = PAGE_SIGNIN
        elif "/post/" in path:
            # 每篇文章一个独立页面（各自的赞/收藏/关注状态互不影响），
            # 这样「第二篇重复一遍」才验得出来是**另一篇**被操作了。
            article_id = path.rsplit("/post/", 1)[-1]
            idx = article_id[-1]  # 末尾数字当序号：…001 / …002 / …003
            if idx == "1":
                body = page_article(article_id, 38, 28)
            elif idx == "2":
                body = page_article(article_id, 14, 7,
                                    title="亿级订单表分库分表设计，从 0 到 1 全流程")
            else:
                body = page_article(article_id, 15, 3,
                                    title="用 WorkBuddy / Codex + Obsidian 搭建自生长的个人知识库实战")
        else:
            # 根路径 = 首页（导航栏在首页上，沸点入口要从这里点）
            body = PAGE_HOME
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
    m.HOME_URL = base + "/"
    m.PINS_URL = base + "/pins"

    # ⚠️ 本机挂着 HTTP_PROXY 又没 NO_PROXY 时，连 chromedriver 的 HTTP 请求都会被代理接管，
    #    报 `unhandled request`（session 能建、但后续每步全挂）。这里同生产脚本一起绕开。
    _bypass_proxy_for_localhost()

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

        # ── 沸点流程（2026-10-01 新增）──
        # T11：从首页导航栏点「沸点」应进入沸点广场（正确入口，不是直接开 URL）
        ok_pins = m._goto_pins_plaza(driver)
        print("[T11] 进沸点广场: %s (%s)" % (ok_pins, driver.current_url))
        if not ok_pins:
            fails.append("T11 没能进入沸点广场，URL=%s" % driver.current_url)

        # T12：反例 —— 抽奖页不得被判成沸点页（双向判据的反例侧）
        driver.get(m.LOTTERY_URL)
        time.sleep(1.0)
        pins_wrong = m._on_pins_page(driver)
        print("[T12] 抽奖页被判为沸点页: %s (期望 False)" % pins_wrong)
        if pins_wrong:
            fails.append("T12 把抽奖页误判成沸点广场")

        # T13：发沸点 —— 内容进框、发布按钮命中（不能是左侧「发布沸点」标题）
        driver.get(base + "/pins")
        time.sleep(1.5)
        pub_status, pub_content = m.publish_pin(driver, "回归测试用的沸点文案")
        print("[T13] 发沸点: status=%r content=%r" % (pub_status, pub_content))
        if pub_status != "已发布沸点":
            fails.append("T13 发沸点应为「已发布沸点」，实得 %r" % pub_status)
        if pub_content != "回归测试用的沸点文案":
            fails.append("T13 发出内容不符，实得 %r" % pub_content)

        # T14：发布框发完必须清空（结构性判据；不清空说明没提交）
        leftover = driver.execute_script(
            "return (document.getElementById('pinEditor').value || '').trim();")
        print("[T14] 发布后输入框残留: %r (期望空)" % leftover)
        if leftover:
            fails.append("T14 发布后输入框应清空，实得 %r" % leftover)

        # T15：新沸点应出现在列表顶部（确认真的发出去了，而非只是框清空）
        first_author = driver.execute_script(
            "var a = document.querySelectorAll('.pin-list .pin-item .author');"
            "return a.length ? (a[0].textContent || '').trim() : '';")
        print("[T15] 列表首位作者: %r (期望 'MacLodge')" % first_author)
        if first_author != "MacLodge":
            fails.append("T15 新沸点未出现在列表顶部，实得 %r" % first_author)

        # T16：点赞两名好友 —— 必须避开「关注」的非好友、已赞的、以及右侧精选栏
        like_status, liked = m.like_friend_pins(driver, 2)
        print("[T16] 点赞: status=%r liked=%r (期望点 2 张、跳过非好友与已赞)"
              % (like_status, liked))
        if "已点赞 2 名好友" != like_status:
            fails.append("T16 应点赞 2 名好友，实得 %r" % like_status)
        # 非好友那张不能被点（它文案里含「这条不是我好友发的」）
        if any("不是我好友" in item for item in liked):
            fails.append("T16 点了非好友的沸点: %r" % liked)
        # 已赞那张不能被重复点
        if any("已经点过赞" in item for item in liked):
            fails.append("T16 重复点了已赞的沸点: %r" % liked)

        # T17：点赞后按钮文案应转为「已赞」（真实生效，而不是空点）
        liked_now = driver.execute_script(
            "var n = 0;"
            "document.querySelectorAll('.pin-list .like-btn').forEach(function(b){"
            "  if ((b.textContent||'').trim() === '已赞') n++; });"
            "return n;")
        print("[T17] 列表里已赞按钮数: %d (期望 >= 3，含原有一条已赞)" % liked_now)
        if liked_now < 3:
            fails.append("T17 点赞未生效，已赞按钮仅 %d 个" % liked_now)

        # T18：右侧「精选沸点」栏的点赞按钮**绝不能被点**（全页模糊匹配会误命中）
        side_liked = driver.execute_script(
            "var n = 0;"
            "document.querySelectorAll('.side-picks .like-btn').forEach(function(b){"
            "  if ((b.textContent||'').trim() === '已赞') n++; });"
            "return n;")
        print("[T18] 精选沸点栏被点数量: %d (期望 0)" % side_liked)
        if side_liked != 0:
            fails.append("T18 误点了右侧精选沸点栏 %d 个" % side_liked)

        # T19：再点一次必须跳过（幂等：已赞的不再点）。
        #     ⚠️ 此时 4 张好友/非好友卡里，能点的只剩第 2 张好友卡 —— 点完不足 2 名，
        #        会走宽松模式。断言的是**绝不重复点已赞的**，不是数量。
        like_again, liked_again = m.like_friend_pins(driver, 2)
        print("[T19] 二次点赞: status=%r liked=%r (期望不重复点已赞)" % (like_again, liked_again))
        if any("已经点过赞" in item for item in liked_again):
            fails.append("T19 二次点赞重复点了已赞的沸点: %r" % liked_again)

        # ── 两遍沸点 + 文章详情页（2026-10-01 第二轮）──
        # T20：固定文案模式下（设了 JUEJIN_PINS_TEXT）两轮文案必须不同，避免被当重复内容
        t1 = m._round_text("测试文案", 1)
        t2 = m._round_text("测试文案", 2)
        print("[T20] 轮次文案: 第1轮=%r 第2轮=%r (期望不同)" % (t1, t2))
        if t1 != "测试文案" or t2 == t1:
            fails.append("T20 轮次文案不符合预期: %r / %r" % (t1, t2))

        # T20b：随机文案池（2026-10-05 追加）—— 20 条池、每次运行随机抽、
        #      同一轮次内不重样、且都取自池内
        saved_pins_text = m.PINS_TEXT
        m.PINS_TEXT = ""
        pool = list(m.PINS_TEXT_POOL)
        if len(pool) != 20 or len(set(pool)) != 20:
            fails.append("T20b 文案池应为 20 条不重复内容，实得 %d 条" % len(pool))
        picked = m.pick_pin_texts(2)
        if len(picked) != 2 or picked[0] == picked[1]:
            fails.append("T20b 两轮文案应抽到不同内容: %r" % (picked,))
        if any(t not in pool for t in picked):
            fails.append("T20b 抽出的文案不在池内: %r" % (picked,))
        # 多跑几次，确认确实在随机（不能恒定同一条）
        seen = set()
        for _ in range(12):
            seen.update(m.pick_pin_texts(1))
        if len(seen) < 5:
            fails.append("T20b 文案池看起来没在随机（12 次只出现 %d 种）" % len(seen))
        print("[T20b] 随机文案池: 池=%d 条 抽2轮=%r 12次出现 %d 种"
              % (len(pool), picked, len(seen)))
        m.PINS_TEXT = saved_pins_text

        # T21：多轮结果折叠文案（两轮相同 → ×2；不同 → 逐轮列）
        same = m._join_rounds(["已发布沸点", "已发布沸点"], "已发布沸点")
        diff = m._join_rounds(["已发布沸点", "发沸点失败（xx）"], "已发布沸点")
        print("[T21] 折叠文案: 相同=%r 不同=%r" % (same, diff))
        if same != "已发布沸点 ×2":
            fails.append("T21 相同结果应折叠为 ×2，实得 %r" % same)
        if "第 1 轮" not in diff or "第 2 轮" not in diff:
            fails.append("T21 不同结果应逐轮列出，实得 %r" % diff)

        # T22：整条沸点流程跑两遍（间隔在生产是 120s，测试里压到 1s 省时间）
        m.PINS_ROUNDS = 2
        m.PINS_ROUND_GAP = 1
        m.PINS_TEXT = ""  # 走随机文案池（默认行为）
        driver.get(base + "/pins")
        time.sleep(1.5)
        pub, content, lk, liked_all = m.pins_activity(driver)
        print("[T22] 两遍沸点: pub=%r content=%r lk=%r" % (pub, content, lk))
        if "×2" not in pub and "第 2 轮" not in pub:
            fails.append("T22 沸点应跑两遍，实得 pub=%r" % pub)
        # 随机文案池：两轮内容应**不同且都不带轮次后缀**（文案本身已不同）
        parts = [c for c in content.split(" / ") if c]
        if len(parts) != 2 or parts[0] == parts[1]:
            fails.append("T22 两轮内容应为两条不同文案: %r" % content)
        if "（2）" in content:
            fails.append("T22 随机文案池下不该加轮次后缀: %r" % content)

        # ── 文章详情页（新标签页 + 第二篇重复）──
        # T23：点第一篇文章 —— ⚠️ 它带 target=_blank，会**新开标签页**。
        #     断言两件事：① 切到了新句柄；② 当前 URL 是文章页。
        driver.get(base + "/")
        time.sleep(1.5)
        handles_before = len(driver.window_handles)
        ok_art = m._goto_nth_article(driver, 1)
        handles_after = len(driver.window_handles)
        print("[T23] 进第1篇: %s 句柄 %d→%d 当前URL=%s"
              % (ok_art, handles_before, handles_after, driver.current_url))
        if not ok_art:
            fails.append("T23 没能进入文章详情页，URL=%s" % driver.current_url)
        if "/post/" not in driver.current_url:
            fails.append("T23 URL 应为 /post/，实得 %s" % driver.current_url)
        if handles_after <= handles_before:
            fails.append("T23 文章应在新标签页打开，句柄数没增加（%d→%d）"
                         % (handles_before, handles_after))
        if "/post/7100000000000000001" not in driver.current_url:
            fails.append("T23 应进入第 1 篇（…001），实得 %s" % driver.current_url)

        # T24：文章点赞 —— 只有图标没有文案，必须靠结构定位
        like_st = m.like_article(driver)
        print("[T24] 第1篇点赞: %r (期望 已点赞文章)" % like_st)
        if like_st != "已点赞文章":
            fails.append("T24 文章点赞应为「已点赞文章」，实得 %r" % like_st)
        like_cnt = driver.execute_script(
            "return document.getElementById('artLike').querySelector('.cnt').textContent;")
        print("[T24] 点赞后计数: %r (期望 39)" % like_cnt)
        if like_cnt != "39":
            fails.append("T24 点赞计数未 +1，实得 %r" % like_cnt)

        # T24b：已赞状态下**再点一次**，绝不能把赞取消掉。
        #      ⚠️ 反推出来的按钮事先不知道是否已赞，而掘金「已赞再点 = 取消」，
        #         全靠脚本「点完复核计数、-1 就补点还原」这段自愈兜住。
        like_again = m.like_article(driver)
        like_cnt2 = driver.execute_script(
            "return document.getElementById('artLike').querySelector('.cnt').textContent;")
        print("[T24b] 再次点赞: status=%r 计数=%r (期望计数仍为 39，不许被取消)"
              % (like_again, like_cnt2))
        if like_cnt2 != "39":
            fails.append("T24b 已赞的文章被误取消（计数变成 %r），自愈逻辑没兜住" % like_cnt2)

        # T25：文章收藏 —— 弹窗选默认收藏夹 → 确定
        #     ⚠️ 详情页别处也有个「确定」（#otherOk），判定必须走收藏窗内的那个
        col_st = m.collect_article(driver)
        print("[T25] 第1篇收藏: %r (期望 已收藏文章)" % col_st)
        if col_st != "已收藏文章":
            fails.append("T25 文章收藏应为「已收藏文章」，实得 %r" % col_st)
        folder = driver.execute_script(
            "return window.savedFolder === null ? '(null)' : window.savedFolder;")
        print("[T25] 存入的收藏夹: %r (期望 '我的收藏')" % folder)
        if "我的收藏" not in str(folder):
            fails.append("T25 应存入默认收藏夹「我的收藏」，实得 %r" % folder)
        modal_shown = driver.execute_script(
            "return document.getElementById('collectMask').style.display !== 'none';")
        print("[T25] 收藏弹窗仍显示: %s (期望 False)" % modal_shown)
        if modal_shown:
            fails.append("T25 点确定后收藏弹窗应关闭")

        # T26：关注作者 —— 右侧作者卡的关注按钮
        fol_st = m.follow_author(driver)
        print("[T26] 第1篇关注: %r (期望 已关注作者)" % fol_st)
        if fol_st != "已关注作者":
            fails.append("T26 关注作者应为「已关注作者」，实得 %r" % fol_st)
        fol_txt = driver.execute_script(
            "return document.getElementById('followBtn').textContent.trim();")
        print("[T26] 关注按钮文案: %r (期望 '已关注')" % fol_txt)
        if fol_txt != "已关注":
            fails.append("T26 关注按钮应变为「已关注」，实得 %r" % fol_txt)

        # T27：已关注状态下再跑必须跳过（绝不能点成取消关注）
        fol_again = m.follow_author(driver)
        print("[T27] 已关注后再跑: %r (期望跳过)" % fol_again)
        if "已关注" not in fol_again:
            fails.append("T27 已关注状态应返回跳过，实得 %r" % fol_again)

        # T28：关标签页 → 必须回到首页标签，且句柄数回到点击前
        m._close_article_tab(driver)
        time.sleep(1)
        print("[T28] 关文章标签后: 句柄 %d，URL=%s"
              % (len(driver.window_handles), driver.current_url))
        if len(driver.window_handles) != handles_before:
            fails.append("T28 关标签后句柄数应回到 %d，实得 %d"
                         % (handles_before, len(driver.window_handles)))
        if "/post/" in driver.current_url:
            fails.append("T28 关标签后应回到首页，实得 %s" % driver.current_url)

        # T29：第二篇 —— 回首页点**另一篇**，重复点赞/收藏
        #     关键断言：进的是 …002，且它的计数从 14→15（不是第一篇的 39）
        ok2 = m._goto_nth_article(driver, 2)
        print("[T29] 进第2篇: %s URL=%s" % (ok2, driver.current_url))
        if not ok2 or "/post/7100000000000000002" not in driver.current_url:
            fails.append("T29 应进入第 2 篇（…002），实得 %s" % driver.current_url)
        like2 = m.like_article(driver)
        col2 = m.collect_article(driver)
        print("[T29] 第2篇: 赞=%r 收藏=%r" % (like2, col2))
        if like2 != "已点赞文章":
            fails.append("T29 第2篇点赞失败，实得 %r" % like2)
        if col2 != "已收藏文章":
            fails.append("T29 第2篇收藏失败，实得 %r" % col2)
        cnt2 = driver.execute_script(
            "return document.getElementById('artLike').querySelector('.cnt').textContent;")
        print("[T29] 第2篇点赞计数: %r (期望 15，证明操作的是另一篇)" % cnt2)
        if cnt2 != "15":
            fails.append("T29 第2篇点赞计数应为 15，实得 %r（可能操作到了同一篇）" % cnt2)
        m._close_article_tab(driver)

        # T30：整条 article_activity 跑 ARTICLE_COUNT=2 篇（端到端）
        m.ARTICLE_COUNT = 2
        a_like, a_col, a_fol = m.article_activity(driver)
        print("[T30] article_activity: 赞=%r 收藏=%r 关注=%r" % (a_like, a_col, a_fol))
        if "×2" not in a_like:
            fails.append("T30 article_activity 应跑 2 篇并折叠 ×2，实得 %r" % a_like)
        if "×2" not in a_col:
            fails.append("T30 收藏也应 ×2，实得 %r" % a_col)
        if len(driver.window_handles) != 1:
            fails.append("T30 跑完后应只剩 1 个标签，实得 %d" % len(driver.window_handles))

        # T31：_article_xpaths 序号替换正确（第 3 篇要取 [3]）
        xp1 = m._article_xpaths(1)[0]
        xp3 = m._article_xpaths(3)[0]
        print("[T31] XPath 序号: 第1篇=%r 第3篇=%r" % (xp1, xp3))
        if "[1]" not in xp1 or "[3]" not in xp3:
            fails.append("T31 _article_xpaths 序号替换不对: %r / %r" % (xp1, xp3))
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
