@echo off
REM 本地开发环境启动脚本

echo ======================================
echo Alpha Strategy V2 - 本地启动
echo ======================================

REM 设置环境变量为本地
set ENV=local

echo 环境: 本地开发 (ENV=local)
echo 数据库: localhost:3306
echo.

REM 进入backend目录并启动
cd backend
python app.py

pause

