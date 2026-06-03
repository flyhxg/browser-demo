@echo off
chcp 65001 >nul
echo Stopping existing Python processes...
taskkill /F /IM python.exe 2>nul
timeout /t 2 >nul
echo Starting backend server...
cd /d D:\work\browser-demo\backend
start "Backend Server" python main.py
echo Backend server started!
