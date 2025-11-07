@echo off
REM 设置UTF-8编码
chcp 65001 > nul 2>&1
title 股票数据导入工具
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║                  股票数据导入与配置更新工具                  ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

echo 准备执行股票数据导入...
echo.
echo 按任意键开始，或关闭窗口取消
pause > nul

echo.
echo 正在执行导入脚本...
echo.

python import_and_update.py

echo.
echo ══════════════════════════════════════════════════════════════
echo.
echo 按任意键退出...
pause > nul

