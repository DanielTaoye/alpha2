@echo off
chcp 65001 >nul
echo ========================================
echo 批量回测 - 后端服务重启脚本
echo ========================================
echo.
echo 正在检查端口5000是否被占用...
netstat -ano | findstr :5000

echo.
echo ========================================
echo 如果看到上面有进程占用5000端口，请：
echo 1. 找到对应的PID（最后一列数字）
echo 2. 在任务管理器中结束该进程
echo 或者在新的命令行窗口运行：
echo    taskkill /F /PID [PID号]
echo ========================================
echo.
echo 按任意键继续...
pause >nul

echo.
echo 正在启动后端服务...
cd backend
python app.py

pause

