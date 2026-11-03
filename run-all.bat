@echo off
start "AutonomaPI Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --reload --port 8000"
start "AutonomaPI Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"
