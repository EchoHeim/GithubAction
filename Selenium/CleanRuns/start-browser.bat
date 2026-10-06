@echo off
chcp 65001 >nul
setlocal

REM ==========================================================================
REM  start-browser.bat
REM  起一个带CDP 调试端口(9222)的 Chrome，供 gh-del-runs.py 接管点击。
REM
REM  为什么要专门起一个：
REM    gh-del-runs.py 靠 CDP 协议操作页面，普通Chrome 没开调试端口连不上。
REM    登录态存在 .browser-profile\ 里，所以第一次要手动登录一次，
REM    之后不用再登。
REM
REM  注意：本脚本会关掉当前所有 Chrome 进程。正在编辑的东西请先保存。
REM ==========================================================================

set PORT=9222
set PROFILE=%~dp0.browser-profile
set REPO_URL=https://github.com/EchoHeim/GithubAction/actions

echo.
echo  [1/3] 检查 9222 端口是否已被占用...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') do (
    echo.
    echo  [!] 端口 %PORT% 已被 PID %%p 占用。
    echo      如果那已经是带调试端口的 Chrome，直接跑清理脚本即可。
    echo      如果不是，先关掉占用它的程序再重试。
    echo.
    pause
    exit /b 1
)
echo        端口空闲
echo.

echo  [2/3] 关闭正在运行的 Chrome...
taskkill /F /IM chrome.exe >nul 2>&1
if errorlevel 1 (
    echo        没有 Chrome 在运行
) else (
    echo        已关闭
)
echo.

echo  [3/3] 启动带调试端口的 Chrome...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=%PORT% ^
    --remote-allow-origins=* ^
    --user-data-dir="%PROFILE%" ^
    "%REPO_URL%"

echo        窗口马上会出来，停在 GitHub Actions 页
echo.

REM 等端口就绪
set /a tries=0
:wait
set /a tries+=1
curl -s -m 2 http://127.0.0.1:%PORT%/json/version >nul 2>&1 && goto ready
if %tries% geq 15 (
    echo  [!] 等了 15 秒端口还没响应，Chrome 可能启动失败
    pause
    exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait

:ready
echo.
echo  ==========================================================================
echo   调试端口 %PORT% 已就绪
echo.
echo   >> 若窗口里显示未登录，请手动登录一次 GitHub
echo      登录态会存在 %PROFILE%%，下次就不用再登
echo   >> 登录完回到这里
echo  ==========================================================================
echo.
pause
exit /b 0
