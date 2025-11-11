@echo off
REM 启动每日机会数据定时同步服务
cd /d %~dp0\..
python backend\scripts\schedule_daily_chance.py
pause

