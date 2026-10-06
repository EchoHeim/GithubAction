#!/usr/bin/env python
"""
gh-del-runs.py —— 通过 CDP 模拟真实鼠标点击，批量删除 GitHub Actions workflow runs。

已验证的页面结构（GitHub 2026-10）：
  行       div.Box-row
  run id   a[href*="/actions/runs/"] 的 href 末段
  名字     a[aria-label] 里 "Run <号> of <workflow名>." —— 唯一可靠来源
            （注意：行内首个链接文字是分支名，不是 workflow 名，别用）
  菜单     details > summary[aria-haspopup="menu"]
  删除项   按钮文本 "Delete workflow run"
  确认框   dialog.Overlay[open] 内的 "Yes, delete this workflow run"
            必须等 showModal，否则 rect 0×0，点了等于没点

用法:
    python gh-del-runs.py --keep 20 --limit 5     # 试删 5 条
    python gh-del-runs.py --keep 20 --limit 0     # 每个 workflow 留 20 条，其余全删
    python gh-del-runs.py --dry-run               # 只统计不删

先决条件: 先用 start-browser.bat 起一个带 9222 调试端口的 Chrome 并登录 GitHub，
详见 README.md。脚本只负责连上去点，不负责起浏览器。
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
from cdp import CDP, _targets  # noqa: E402

LOGFILE = None
NAME_RE = re.compile(r"Run\s+\d+\s+of\s+(.+?)\.")


def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    if LOGFILE:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def get_cdp():
    pages = [t for t in _targets()
             if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        sys.exit("找不到页面。确认 Chrome 是用 --remote-debugging-port=9222 启动的。")
    return CDP(pages[0]["webSocketDebuggerUrl"])


# 一次抓完整页的 run 信息。名字来自 aria-label，不是链接文字。
JS_ROWS = r'''JSON.stringify(
  [...document.querySelectorAll("div.Box-row")].map((r, i) => {
    const a = r.querySelector('a[href*="/actions/runs/"]');
    const aria = r.querySelector("[aria-label]")?.getAttribute("aria-label") || "";
    const m = aria.match(/Run\s+\d+\s+of\s+(.+?)\./);
    const no = (aria.match(/Run\s+(\d+)/) || [])[1] || null;
    return {
      idx: i,
      runId: a ? a.getAttribute("href").split("/").pop() : null,
      name: m ? m[1].trim() : null,
      runNo: no,
      // 运行中的行没有删除菜单
      status: /currently running/i.test(aria) ? "running"
            : (/queued|waiting|requested|pending/i.test(aria) ? "queued" : "done")
    };
  }).filter(x => x.runId && x.name)
)'''


class Deleter:
    def __init__(self, cdp, owner, repo, keep):
        self.c = cdp
        self.owner, self.repo = owner, repo
        self.keep = keep
        self.deleted = 0
        self.page = 1

    # ---------- 基础 ----------
    def total(self):
        return self.c.js(
            'document.body.innerText.match(/([0-9,]+) workflow runs/)?.[1]'
            '?.replace(/,/g, "") || null')

    def rows(self):
        return json.loads(self.c.js(JS_ROWS))

    def go_actions(self):
        self.c.nav(f"https://github.com/{self.owner}/{self.repo}/actions")
        time.sleep(5)
        self.page = 1

    def click(self, find_js):
        r = self.c.js(find_js)
        if not r:
            return "NOT_FOUND"
        b = json.loads(r)
        if b.get("w", 0) < 1 or b.get("h", 0) < 1:
            return "ZERO_SIZE"
        for ev in ("mousePressed", "mouseReleased"):
            self.c.send("Input.dispatchMouseEvent", type=ev,
                        x=b["x"], y=b["y"], button="left", clickCount=1)
        return "CLICKED"

    # ---------- 删除一条 ----------
    def delete_row(self, idx):
        # summary 贴视口底边时点不中（GitHub 的 <summary> 命中区很窄），
        # 先把它滚到视口正中，再派发鼠标事件
        r1 = self.click(f'''(() => {{
          const r = [...document.querySelectorAll("div.Box-row")][{idx}];
          if (!r) return null;
          const s = r.querySelector('details summary');
          if (!s) return null;
          s.scrollIntoView({{block:"center", inline:"center"}});
          const b = s.getBoundingClientRect();
          if (b.width < 1 || b.height < 1) return null;
          // 命中点必须离视口边缘有余量
          if (b.top < 60 || b.bottom > window.innerHeight - 20) return null;
          return JSON.stringify({{x:b.x+b.width/2, y:b.y+b.height/2, w:b.width, h:b.height}});
        }})()''')
        if r1 != "CLICKED":
            # 兜底：直接置 open。菜单项本就在 DOM 里，只是被 CSS 收起
            forced = self.c.js(f'''(() => {{
              const r = [...document.querySelectorAll("div.Box-row")][{idx}];
              const d = r && r.querySelector("details");
              if (!d) return null;
              d.open = true;
              return d.open ? "FORCED" : "FAILED";
            }})()''')
            if forced != "FORCED":
                return False, f"菜单:{r1}/{forced}"
            time.sleep(0.6)
        time.sleep(0.9)

        r2 = self.click(f'''(() => {{
          // 只认第 {idx} 行自己的 details，避免抓到别的行
          const row = [...document.querySelectorAll("div.Box-row")][{idx}];
          const d = row && row.querySelector("details[open]");
          if (!d) return null;
          const b = [...d.querySelectorAll("button")].find(
            e => /^\\s*Delete workflow run\\s*$/i.test(e.textContent || ""));
          if (!b) return null;
          // 菜单常渲染在视口外（列表底部行的菜单向上弹），必须先滚进来
          b.scrollIntoView({{block:"center"}});
          const r = b.getBoundingClientRect();
          if (r.width < 1 || r.height < 1) return null;
          if (r.top < 0 || r.bottom > window.innerHeight) return null;
          return JSON.stringify({{x:r.x+r.width/2, y:r.y+r.height/2, w:r.width, h:r.height}});
        }})()''')
        if r2 != "CLICKED":
            return False, f"删除项:{r2}"
        time.sleep(1.4)

        # 等 dialog 真正 showModal，否则按钮 rect 为 0
        for _ in range(10):
            box = self.c.js('''(() => {
              const dlg = [...document.querySelectorAll("dialog.Overlay")]
                .find(d => d.hasAttribute("open"));
              if (!dlg) return null;
              const b = [...dlg.querySelectorAll("button")].find(
                e => /Yes, delete this workflow run/i.test(e.textContent || ""));
              if (!b) return null;
              const r0 = b.getBoundingClientRect();
              // 必须完整落在视口内，否则点了也是白点
              const vh = window.innerHeight, vw = window.innerWidth;
              if (r0.top < 0 || r0.bottom > vh || r0.left < 0 || r0.right > vw) {
                b.scrollIntoView({block:"center"});
              }
              const r = b.getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2, y:r.y+r.height/2, w:r.width, h:r.height,
                                     vh, vw, top:r.top, bot:r.bottom});
            })()''')
            if box:
                b = json.loads(box)
                # 尺寸非 0 且中心点在视口内，才点
                if b.get("w", 0) > 0 and 0 < b["y"] < b.get("vh", 0):
                    for ev in ("mousePressed", "mouseReleased"):
                        self.c.send("Input.dispatchMouseEvent", type=ev,
                                    x=b["x"], y=b["y"], button="left", clickCount=1)
                    return True, "ok"
            time.sleep(0.4)
        return False, "确认框未出现"

    # ---------- 找本页该删的行 ----------
    def target_idx(self):
        """按 aria-label 得到的 workflow 名分组，排名 > keep 且已完成的行"""
        return self.c.js(f'''(() => {{
          const KEEP = {self.keep};
          const rows = [...document.querySelectorAll("div.Box-row")];
          const seen = {{}};
          for (let i = 0; i < rows.length; i++) {{
            const r = rows[i];
            const a = r.querySelector('a[href*="/actions/runs/"]');
            if (!a) continue;
            const aria = r.querySelector("[aria-label]")?.getAttribute("aria-label") || "";
            const m = aria.match(/Run\\s+\\d+\\s+of\\s+(.+?)\\./);
            if (!m) continue;                    // 名字拿不到就不动，宁可漏删
            const name = m[1].trim();
            if (/currently running/i.test(aria)) continue;   // 运行中不删
            seen[name] = (seen[name] || 0) + 1;
            if (seen[name] > KEEP) return i;
          }}
          return -1;
        }})()''')

    def last_page(self):
        m = self.c.js(
            'Math.max(0, ...[...document.querySelectorAll("a")].map(a => '
            '(a.getAttribute("href")||"").match(/[?&]page=(\\d+)/)?.[1])'
            '.filter(Boolean).map(Number)) || 0')
        return m or 1

    def goto_page(self, n):
        self.c.nav(f"https://github.com/{self.owner}/{self.repo}/actions?page={n}")
        time.sleep(4.5)

    # ---------- 主循环 ----------
    def run(self, limit, delay, dry):
        self.go_actions()
        start = self.total()
        log(f"起始 {start} 条| 每 workflow 保留 {self.keep} 条 | 上限 {limit or '不限'}")
        self._census(start)

        if dry:
            log("DRY RUN，不删除")
            return

        stall = 0
        last = start
        lastpage = self.last_page()
        log(f"共{lastpage} 页")
        while limit == 0 or self.deleted < limit:
            idx = self.target_idx()

            if idx == -1:
                if self.page < lastpage:
                    self.page += 1
                    self.goto_page(self.page)
                    stall = 0
                    continue
                log(f"✓ 全部 {lastpage} 页扫完，只剩保留条数。共删 {self.deleted} 条")
                break

            info = self.rows()[idx]
            ok, why = self.delete_row(idx)
            if not ok:
                log(f"[停] {info['name']} #{info['runNo']} 删除失败: {why}")
                self.c.shot(f"fail-{self.deleted}.png")
                break

            self.deleted += 1
            time.sleep(1.0)
            if delay:
                time.sleep(delay)

            if self.deleted % 10 == 0:
                cur = self.total()
                log(f"  已删 {self.deleted} | 剩余 {cur} | 第{self.page}页")
                if cur is not None and last is not None and cur >= last:
                    stall += 1
                    if stall >= 3:
                        log("连续 3 次总数不降，卡住，停")
                        break
                else:
                    stall = 0
                last = cur

        log(f"完成：删除 {self.deleted} 条，剩余 {self.total()}")

    def _census(self, total):
        """第一页的名字分布，用来验证解析对不对"""
        rows = self.rows()
        from collections import Counter
        cnt = Counter(r["name"] for r in rows)
        log("本页 workflow 分布: " + ", ".join(f"{k}×{v}" for k, v in cnt.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=20)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--owner", default="EchoHeim")
    ap.add_argument("--repo", default="GithubAction")
    a = ap.parse_args()

    LOGFILE = f"gh-runs-delete-{datetime.now():%Y%m%d-%H%M%S}.log"
    cdp = get_cdp()
    cdp.send("Page.enable")
    log(f"连接 {a.owner}/{a.repo} | {cdp.js('location.href')}")
    log(f"日志 {LOGFILE}")
    try:
        Deleter(cdp, a.owner, a.repo, a.keep).run(a.limit, a.delay, a.dry_run)
    except KeyboardInterrupt:
        log("中断")
    finally:
        cdp.shot("final-state.png")
        cdp.close()
