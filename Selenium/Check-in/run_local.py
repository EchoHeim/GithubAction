# -*- coding: UTF-8 -*-
"""本地运行器：让签到脚本脱离 GitHub Actions 在本机跑。

CI 上凭据来自 GitHub Secrets，以命令行参数传给签到脚本；本机没有 Secrets，
所以凭据放在同目录的 .env.local（已 gitignore），由本脚本读取后透传。

用法：
    python Selenium/Check-in/run_local.py            # 默认跑聚宽（定时任务用的就是这条）
    python Selenium/Check-in/run_local.py 52pojie    # 跑吾爱破解
    python Selenium/Check-in/run_local.py juejin     # 跑掘金

不带参数时行为与历史版本完全一致（聚宽 + joinquant-YYYY-MM-DD.log），
计划任务 JoinQuantCheckIn 不受影响。

退出码沿用签到脚本的退出码；输出同时打印到控制台并落盘到 logs/。
"""

import datetime
import os
import pathlib
import subprocess
import sys

# 站点表：
#   module   要跑的签到模块
#   args     以命令行参数传给模块的凭据项（按顺序）；52pojie 走环境变量，所以是空的
#   required 凭据要求，**任一** 元组被完整满足即可（多个元组 = 多选一）
#   log/title 日志名与表头
SITES = {
    "joinquant": {
        "module": "Selenium.Check-in.JoinQuant",
        "args": ("JQ_USERNAME", "JQ_PASSWORD", "FEISHU_BOT_ID"),
        "required": (("JQ_USERNAME", "JQ_PASSWORD"),),
        "log": "joinquant",
        "title": "聚宽签到",
    },
    "52pojie": {
        # 只用 Cookie 登录（密码登录已移除：登录页是 Cloudflare Turnstile，本机线路到不了它）
        "module": "Selenium.Check-in.52pojie",
        "args": (),
        "required": (("PJ52_COOKIE",),),
        "log": "52pojie",
        "title": "52pojie 签到",
    },
    "juejin": {
        # 走账号密码（脚本会自动过字节滑块验证码）；Cookie 作为可选兜底。
        "module": "Selenium.Check-in.juejin",
        "args": (),
        "required": (("JUEJIN_USERNAME", "JUEJIN_PASSWORD"), ("JUEJIN_COOKIE",)),
        "log": "juejin",
        "title": "掘金签到",
    },
}
DEFAULT_SITE = "joinquant"

# 计划任务里用 pythonw 启动时没有控制台，sys.stdout 为 None，print 会直接抛异常
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

# 输出被重定向到文件或管道时默认是块缓冲，日志会滞后甚至乱序
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # 仓库根，-m 必须从根目录起跑
ENV_FILE = HERE / ".env.local"
LOG_DIR = HERE / "logs"

# Selenium 的 urllib3 会把 http_proxy 套到发往 localhost:chromedriver 的请求上，
# 代理回一句 "unhandled request"，现象是能建会话但任何命令都失败。
# Chrome 自身走系统代理设置、不读这些变量，所以清掉不影响它访问外网。
PROXY_KEYS = (
    "http_proxy",
    "https_proxy",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "all_proxy",
    "ALL_PROXY",
)

FAIL_MARKERS = ("登录失败", "签到失败", "积分领取失败", "无法", "未通过", "无法识别", "不是登录态")


def load_env(path):
    """读取 KEY=VALUE 形式的凭据文件；不使用 shell 解析，避免密码里的特殊字符被吃掉。"""
    if not path.exists():
        sys.exit(
            "[X] 缺少凭据文件: %s\n"
            "    从 .env.local.example 复制一份，填入账号密码后再跑。" % path
        )

    env = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            print("[WARN] %s:%d 不是 KEY=VALUE，已跳过" % (path.name, lineno))
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        # 允许用引号包住含空格的密码
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env[key.strip()] = value
    return env


def check_required(env, site):
    """按站点要求校验凭据：required 里**任一**元组被完整满足即可。

    飞书机器人 ID 不在这里校验 —— 三个签到脚本都把它当可选项，没配只是不推卡片。
    """
    groups = site["required"]
    if any(all(env.get(key) for key in group) for group in groups):
        return
    options = " 或 ".join(" + ".join(group) for group in groups)
    sys.exit(
        "[X] 凭据文件里缺少 %s 的凭据，需要: %s\n"
        "    对着 .env.local.example 补齐再跑。" % (site["title"], options)
    )


def build_child_env(creds):
    env = os.environ.copy()
    for key in PROXY_KEYS:
        env.pop(key, None)
    env["NO_PROXY"] = "localhost,127.0.0.1"
    env["no_proxy"] = "localhost,127.0.0.1"
    # 子进程的 print 全是中文，管道默认按 GBK 编码会让父进程解出乱码
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(creds)
    # 固定浏览器 profile，把登录 cookie 留住 —— 否则每天冷启动都要重过一遍登录风控。
    # 三个站点共用一份：cookie 按域隔离，互不干扰，又能各自复用会话。
    env.setdefault("CHECKIN_PROFILE_DIR", str(HERE / ".browser-profile"))
    return env


def pick_site(name):
    if name not in SITES:
        sys.exit(
            "[X] 未知站点: %s\n    可选: %s" % (name, ", ".join(sorted(SITES)))
        )
    return SITES[name]


def main():
    site_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SITE
    site = pick_site(site_name)

    creds = load_env(ENV_FILE)
    check_required(creds, site)

    argv = [
        sys.executable,
        "-B",
        # -u: 不加的话子进程 stdout 走块缓冲，traceback 会先于正文冒出，日志读起来是乱的
        "-u",
        "-m",
        site["module"],
    ] + [creds.get(key, "") for key in site["args"]]
    env = build_child_env(creds)

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / ("%s-%s.log" % (site["log"], datetime.date.today().isoformat()))

    headless = "开启（不弹窗口）" if creds.get("CHECKIN_HEADLESS") == "1" else "关闭（会弹出浏览器）"
    header = [
        "=" * 60,
        "%s · 本地运行 %s" % (site["title"], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "工作目录: %s" % ROOT,
        "解释器  : %s" % sys.executable,
        "无头模式: %s" % headless,
        "=" * 60,
    ]

    lines = []
    with log_path.open("a", encoding="utf-8") as log:
        for line in header:
            print(line)
            log.write(line + "\n")

        proc = subprocess.Popen(
            argv,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for line in proc.stdout:
            line = line.rstrip("\n")
            print(line)
            log.write(line + "\n")
            lines.append(line)
        code = proc.wait()

        fails = [line for line in lines if any(m in line for m in FAIL_MARKERS)]
        tail = "" if code == 0 else "（退出码 %d）" % code
        if fails:
            summary = "结束：检测到 %d 处失败标记%s" % (len(fails), tail)
            for line in fails[:5]:
                summary += "\n    " + line.strip()
        else:
            summary = "结束：未发现失败标记%s" % tail

        print(summary)
        log.write(summary + "\n")
        log.write("日志: %s\n" % log_path)

    return code


if __name__ == "__main__":
    sys.exit(main())
