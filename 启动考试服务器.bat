@echo off
chcp 65001 >nul
title 冉鹏工作室 - 考试服务器
echo.
echo ========================================
echo   冉鹏工作室 - 考试服务器 v2.19.0
echo ========================================
echo.
echo   正在启动，请稍候...
echo.
echo   （关闭此窗口即可停止服务器）
echo.
echo ========================================
echo.
"C:\Users\DAI JUN\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0server.py"
pause
