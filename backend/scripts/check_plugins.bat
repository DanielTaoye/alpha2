@echo off
chcp 65001 > nul
echo ========================================
echo 检查12月3日触发插件的股票
echo ========================================
echo.
echo 请确保后端服务已启动 (http://localhost:5000)
echo.
pause

cd /d %~dp0
python check_plugins_triggered.py

echo.
echo.
echo 检查完成，按任意键退出...
pause > nul

