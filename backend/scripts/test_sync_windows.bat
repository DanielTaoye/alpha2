@echo off
chcp 65001 >nul
echo ========================================
echo 测试同步任务（立即执行一次）
echo ========================================
echo.

cd /d %~dp0..\..

python backend\scripts\daily_chance_scheduler_test.py

echo.
echo ========================================
echo 测试完成
echo ========================================
pause

