@echo off
chcp 65001 >nul
echo ========================================
echo 刷新 b_daily_chance 表最新一天数据
echo ========================================
echo.

cd /d %~dp0
cd backend\scripts

REM 默认处理59支股票，若需全部股票请使用 --all 参数
python refresh_daily_chance.py %*

echo.
echo 按任意键退出...
pause >nul
