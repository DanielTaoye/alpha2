@echo off
echo ============================================================
echo 同步最新一周数据到生产主库
echo ============================================================
echo.
echo 主库：sh-cdb-2hxu41ka.sql.tencentcdb.com:21648
echo 股票数量：59支（波段20 + 短线20 + 中长线19）
echo 同步范围：最近7天的数据
echo 包含：赔率总分、支撑线、压力线、成交量类型
echo.
echo 按任意键开始同步...
pause >nul

cd backend
python scripts/sync_latest_daily_chance_to_production.py

echo.
echo ============================================================
echo 同步完成
echo ============================================================
pause

