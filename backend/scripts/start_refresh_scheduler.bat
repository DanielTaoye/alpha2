@echo off
chcp 65001
cd C:\Users\lenovo\Desktop\alpha_strategy_v2\backend\scripts
if not exist logs mkdir logs
echo 启动定时任务：刷新成交量类型和K线组合
echo 定时任务配置: 每天 17:00 执行
echo.
python refresh_volume_type_production.py --scheduler
pause

