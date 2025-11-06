@echo off
echo ========================================
echo   阿尔法策略2.0系统 安装脚本
echo ========================================
echo.

echo 正在检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo Python未安装或未添加到PATH环境变量
    echo 请先安装Python 3.7+
    pause
    exit /b 1
)

echo.
echo 正在安装依赖包...
pip install -r requirements.txt

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   依赖安装成功！
    echo ========================================
    echo.
    echo 下一步操作：
    echo 1. 修改 backend/app.py 中的数据库配置
    echo 2. 确保MySQL数据库服务已启动
    echo 3. 运行 start.bat 启动系统
    echo.
) else (
    echo.
    echo 依赖安装失败，请检查网络连接或pip配置
)

pause

