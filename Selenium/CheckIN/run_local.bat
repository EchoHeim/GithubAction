@echo off
REM 聚宽签到 · 本机运行入口
REM 手动双击可跑；Windows 任务计划程序也调这个文件。
REM 凭据从同目录的 .env.local 读，不在本文件里硬编码。

setlocal
set "REPO=%~dp0..\.."
set "PY=C:\Users\Lodge\.workbuddy\binaries\python\envs\checkin\Scripts\python.exe"

if not exist "%PY%" (
    echo [X] 找不到签到专用虚拟环境: %PY%
    echo     用下面这条命令重建：
    echo     "C:\Users\Lodge\AppData\Local\Programs\Python\Python314\python.exe" -m venv "%PY%\.."
    exit /b 1
)

cd /d "%REPO%"
"%PY%" -B "Selenium\CheckIN\run_local.py"
exit /b %ERRORLEVEL%
