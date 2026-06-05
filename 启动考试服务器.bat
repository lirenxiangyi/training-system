@echo off
chcp 65001 >nul
title 冉鹏工作室 - 考试服务器
echo.
echo ========================================
echo   冉鹏工作室 - 考试服务器 v2.19.0
echo ========================================
echo.

REM 检查端口8080是否被占用
netstat -ano | findstr ":8080" >nul
if %errorlevel% == 0 (
    echo   [警告] 端口8080已被占用！
    echo.
    echo   可能的原因：
    echo   1. 服务器已经在运行（请检查其他黑色命令窗口）
    echo   2. 其他程序占用了8080端口
    echo.
    echo   解决方法：
    echo   - 关闭其他服务器窗口后重试
    echo   - 或打开任务管理器结束 python.exe 进程
    echo.
    pause
    exit /b
)

echo   正在启动，请稍候...
echo.
echo   （关闭此窗口即可停止服务器）
echo.
echo ========================================
echo.

REM 启动服务器（在新窗口中打开浏览器，带缓存清除参数）
start "" "http://localhost:8080/?v=2190"

"C:\Users\DAI JUN\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0server.py"
pause
