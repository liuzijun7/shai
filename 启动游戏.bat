@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py main.py
    exit /b
)
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
    exit /b
)
echo 未找到 Python。请安装 Python 3.11 或更高版本，并勾选 Add Python to PATH。
pause
