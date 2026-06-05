@echo off
title ExamServer_v2.19.0
start "" "http://localhost:8080/?nocache=1"
"C:\Users\DAI JUN\.workbuddy\binaries\python\versions\3.13.12\python.exe" "%~dp0server.py"
echo Server stopped.
pause
