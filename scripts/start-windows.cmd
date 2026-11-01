@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    echo First run setup-windows.cmd
    pause
    exit /b 1
)
start "Classroom" http://127.0.0.1:8000
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload
pause
