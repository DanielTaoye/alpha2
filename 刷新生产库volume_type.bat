@echo off
chcp 65001 >nul
echo ===================================================
echo 刷新生产库 b_daily_chance 表最近3个月的 volume_type
echo ===================================================
echo.

cd /d "%~dp0"
cd backend\scripts

echo 正在执行刷新脚本...
echo.

python refresh_volume_type_production.py

echo.
echo ===================================================
echo 执行完成！
echo ===================================================
pause

