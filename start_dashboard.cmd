@echo off
title CyberClaw Web Dashboard
color 0A
echo ============================================================
echo          LAUNCHING CYBERCLAW DASHBOARD
echo ============================================================
call .venv\Scripts\activate.bat
echo Starting server on http://localhost:8000/ui ...
cyberclaw gateway start
pause
