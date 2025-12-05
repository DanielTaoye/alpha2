@echo off
chcp 65001
cd C:\Users\lenovo\Desktop\alpha_strategy_v2\backend\scripts
if not exist logs mkdir logs
echo ========================================
echo 刷新生产库 b_daily_chance 表数据
echo 刷新内容: 成交量类型 + 多头组合 + 空头组合
echo ========================================
echo.
python refresh_volume_type_production.py %*
pause

