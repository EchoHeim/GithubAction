# -*- coding: UTF-8 -*-
"""本地运行器：让签到脚本脱离 GitHub Actions 在本机跑。

CI 上凭据来自 GitHub Secrets，以命令行参数传给签到脚本；本机没有 Secrets，
所以凭据放在同目录的 .env.local（已 gitignore），由本脚本读取后透传。

用法：
    python ChromeSelenium/Check-in/run_local.py

退出码沿用签到脚本的退出码；输出同时打印到控制台并落盘到 logs/。
"""

import datetime
import os
import pathlib
import subprocess
import sys

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

TARGET_MODULE = "ChromeSelenium.Check-in.JoinQuant"
REQUIRED_KEYS = ("JQ_USERNAME", "JQ_PASSWORD", "FEISHU_BOT_ID")

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

FAIL_MARKERS = ("登录失败", "签到失败", "积分领取失败", "无法")


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


def check_required(env):
    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    if missing:
        sys.exit(
            "[X] 凭据文件里缺少: %s\n"
            "    对着 .env.local.example 补齐再跑。" % ", ".join(missing)
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
    # 固定浏览器 profile，把聚宽的登录 cookie 留住 —— 否则每天冷启动都要重过一遍登录风控
    env.setdefault("CHECKIN_PROFILE_DIR", str(HERE / ".browser-profile"))
    return env


def main():
    creds = load_env(ENV_FILE)
    check_required(creds)

    argv = [
        sys.executable,
        "-B",
        # -u: 不加的话子进程 stdout 走块缓冲，traceback 会先于正文冒出，日志读起来是乱的
        "-u",
        "-m",
        TARGET_MODULE,
        creds["JQ_USERNAME"],
        creds["JQ_PASSWORD"],
        creds["FEISHU_BOT_ID"],
    ]
    env = build_child_env(creds)

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / ("joinquant-%s.log" % datetime.date.today().isoformat())

    headless = "开启（不弹窗口）" if creds.get("CHECKIN_HEADLESS") == "1" else "关闭（会弹出浏览器）"
    header = [
        "=" * 60,
        "聚宽签到 · 本地运行 %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
