@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   局域网云盘 · 正在启动
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 没有找到 python，请先安装 Python 3.9+ 并勾选 Add to PATH
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn, multipart" >nul 2>nul
if errorlevel 1 (
    echo [提示] 首次运行，正在安装依赖...
    python -m pip install -r requirements.txt
)

REM 如需访问口令，取消下面这行的注释并改成自己的密码
REM set LAN_DISK_PASSWORD=123456

REM 如需换端口（默认 8101），取消下面这行的注释
REM set LAN_DISK_PORT=9000

python main.py

echo.
echo 服务已停止
pause
