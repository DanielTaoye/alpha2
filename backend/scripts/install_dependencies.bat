@echo off
chcp 65001
echo ==========================================
echo 安装Python依赖包
echo ==========================================
echo.

cd C:\Users\lenovo\Desktop\alpha_strategy_v2

echo 安装依赖包...
pip install APScheduler

echo.
echo ==========================================
echo 安装完成！
echo ==========================================
echo.
echo 验证安装:
python -c "import apscheduler; print('✅ APScheduler 已安装')"
echo.
pause

