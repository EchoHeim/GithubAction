# CleanRuns —— 批量删除 GitHub Actions workflow runs

浏览器模拟点击版。用CDP 协议驱动一个真实 Chrome，按 GitHub 界面上的按钮来删 run，
不碰 API token。

**实测有效**：2026-10-06 在 `EchoHeim/GithubAction` 上从 939 条删到 930 条，5 条零失败，
页面出现绿色横幅 `Workflow run deleted successfully.`（见 `screenshot-proof.png`）。

---

## 快速开始

```bat
:: 1. 起浏览器（首次要手动登录一次 GitHub）
start-browser.bat

:: 2. 试删 5 条，确认没问题
python run_local.py

:: 3. 满意后全量删（每个 workflow 留 20 条）
python run_local.py --full
```

或者直接调底层脚本：

```bat
python gh-del-runs.py --keep 20 --limit 5      :: 试删 5 条
python gh-del-runs.py --keep 20 --limit 0      :: 全量
python gh-del-runs.py --keep 20 --limit 0 --dry-run   :: 只统计不删
python gh-del-runs.py --keep 50 --limit 0      :: 每个 workflow 留 50 条
python gh-del-runs.py --keep 20 --limit 100 --delay 1  :: 慢删，限速
```

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `run_local.py` | 一键入口，负责检查端口、起浏览器、转发参数 |
| `start-browser.bat` | 起带 9222 调试端口的 Chrome，登录态存`.browser-profile/` |
| `gh-del-runs.py` | 主程序。翻页 + 定位该删的行 + 模拟点击删除 |
| `cdp.py` | 极简 CDP 客户端，直接跟 Chrome 说 WebSocket 协议 |
| `.browser-profile/` | 浏览器 profile，**含登录 cookie，严禁入库**（已配 .gitignore） |
| `screenshot-proof.png` | 成功截图 |

---

## 为什么要用 CDP 而不是 Selenium

`CleanWorkflows.py`（同目录上一级）就是 Selenium 版，思路一样，但用绝对 XPath：

```
/html/body/div[1]/div[5]/div/main/turbo-frame/.../li[2]/dialog-helper/dialog/div[2]/form/button/span/span
```

这种路径 GitHub 改一次布局就全废，而且它删到一半崩了你不会知道 —— 整个循环包在
`try/except` 里，`break` 掉了事。

这版改成：
- **用语义定位**（`aria-label` 文本、`details[open]`、`dialog.Overlay[open]`），GitHub 改版布局还能活
- **每删一条都校验总数**，连续 3 次不下降就判定卡住并停下
- **失败截图 + 日志**，出问题能查
- **复用已登录的浏览器**，不传密码

代价：需要手动起一次带调试端口的 Chrome，不能像 Selenium 那样 `webdriver.Chrome()` 一把梭。

---

## GitHub 页面结构备忘（2026-10 实测）

改版频繁，这里记录踩过的坑，改版后按这个重新核对：

| 目标 | 定位方式 |
|---|---|
| 行 | `div.Box-row`（**不是** `div[data-testid="workflow-run"]`） |
| run id | `a[href*="/actions/runs/"]` 的 href 末段 |
| **workflow 名** | `[aria-label]` 里 `Run <号> of <名字>.` —— **唯一可靠来源** |
| 菜单 | `details > summary[aria-haspopup="menu"]` |
| 删除项 | 按钮文本 `Delete workflow run` |
| 确认框 | `dialog.Overlay[open]` 内按钮 `Yes, delete this workflow run` |
| 分页 | URL `?page=N`，每页 25 条，939 条共 38 页 |

### 三个把人坑了的点

**1. 行内第一个链接的文字是分支名，不是 workflow 名。**

```
aria-label = "failed:  Run 7065 of 富途种子. 45"
                        ↑workflow 名     ↑ 分支名
```

如果按行文本切分来取名字，会得到「45 富途种子」和「富途种子」两个不同名字，
keep 判定全失效 → 无限翻页空转。这个 bug 调了很久。

**2. 确认框必须等 `showModal()`，否则按钮尺寸是 0×0。**

```js
document.querySelector("dialog.Overlay[open]")   // [open] 属性必须有
```

`details[open]` 里的菜单项也可能在视口外（列表底部行的菜单向上弹），
必须 `scrollIntoView` 之后再派发鼠标事件。

**3. `summary` 贴视口底边时点不中。**

GitHub的 `<summary>` 命中区很窄，贴边时点击落空。脚本会保证命中点距视口边缘有余量
（top > 60，bottom < innerHeight - 20），点不中就直接 `details.open = true` 兜底。

---

## 常见问题

**Q: `agent-browser` 能不能用？**
试过，CLI 命令在这台机器上频繁 SIGTERM，有一条 `open` 挂了 8 分钟
（页面早打开了，就是输出管道不关）。所以改成Python 直连 CDP，稳定。

**Q: 能复用我日常 Chrome 的登录态吗？**
试过 `--profile Default`，**不行** —— 那个 profile 没登录 GitHub，
私有库对未登录用户直接返回 404，连「请登录」都不给。
所以用独立的 `.browser-profile/`，第一次手动登一次就行。

**Q: 跑一半断了怎么办？**
日志在同目录 `gh-runs-delete-*.log`，里面记了每条删除时间。重跑会从头开始，
因为 keep 是按 workflow 排名算的，已经删掉的不影响正确性。

**Q: 删错了能恢复吗？**
**不能。** GitHub 没有回收站，run 记录和日志是当场消失的。
所以第一次务必先跑 `--limit 5`。

---

## 治本：别让run 再堆起来

删干净只是治标。根因是定时任务还在跑，而保留期限是默认 90 天。

`Settings` → `Actions` → `General` → **Maximum retention period** 拉短
（artifact 和 log 分开设）。设了之后 GitHub 的后台清理任务会定期扫，
有延迟，通常几小时到一天。

不做这一步，下个月又是几百条。
