@echo off
title Sutawane Classes - Local WhatsApp Bridge
echo ========================================================
echo   SUTAWANE CLASSES MANAGEMENT SOFTWARE
echo   Starting Local WhatsApp Web Gateway Service (Port 3000)...
echo ========================================================
echo.
cd /d "%~dp0whatsapp_bridge"
if not exist node_modules (
    echo [Setup] Installing local dependencies...
    call npm install
)
node server.js
pause
