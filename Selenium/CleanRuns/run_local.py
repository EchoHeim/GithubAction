#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""
run_local.py —— CleanRuns 模块的本地一键入口。

跟 CheckIN/run_local.py 同一套用法：直接跑，按提示操作。

    python run_local.py# 走默认流程：起浏览器 -> 试删 5 条
    python run_local.py --full        # 全量：每个 workflow 留 20 条
    python run_local.py --keep 50     # 改成留 50 条
    python run_local.py --dry-run     # 只统计不删
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 9222


def port_alive():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def ensure_browser():
    if port_alive():
        print(f"[OK] {PORT} 端口已有浏览器在跑")
        return True
    print(f"[!] {PORT} 端口没响应，尝试启动浏览器...")
    bat = os.path.join(HERE, "start-browser.bat")
    if not os.path.exists(bat):
        print(f"[X] 找不到 {bat}")
        return False
    subprocess.call(["cmd", "/c", bat], shell=False)
    return port_alive()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=20, help="每个 workflow 保留最近 N 条")
    ap.add_argument("--full", action="store_true", help="全量删除（等价 --limit 0）")
    ap.add_argument("--dry-run", action="store_true", help="只统计不删")
    ap.add_argument("--delay", type=float, default=0, help="每条之间额外等待秒")
    a = ap.parse_args()

    limit = 0 if a.full else 5

    print("=" * 66)
    print(" GitHub Actions workflow run 批量清理")
    print(f" 仓库     : EchoHeim/GithubAction")
    print(f" 保留     : 每个 workflow 最新 {a.keep} 条")
    print(f" 本次删除 : {'全量' if limit == 0 else f'最多 {limit} 条'}")
    print("=" * 66)

    if not ensure_browser():
        print("\n[X] 浏览器没起来，先手动跑 start-browser.bat 看看")
        return 1

    time.sleep(1)
    script = os.path.join(HERE, "gh-del-runs.py")
    cmd = [sys.executable, "-u", script, "--keep", str(a.keep), "--limit", str(limit)]
    if a.dry_run:
        cmd.append("--dry-run")
    if a.delay:
        cmd += ["--delay", str(a.delay)]

    print(f"\n[运行] {' '.join(cmd)}\n")
    rc = subprocess.call(cmd)
    print("\n[结束] 返回码", rc)
    if rc == 0 and not a.dry_run:
        print("提醒：去Settings -> Actions -> General 把 Maximum retention period")
        print("      拉短，否则定时任务还会继续堆积 run。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
