@echo off
chcp 65001 > nul
echo ========================================
echo 检查触发插件的股票（精简版）
echo ========================================
echo.

cd /d %~dp0
python check_plugins_simple.py

echo.
pause

