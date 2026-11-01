@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    py -3.12 -m venv .venv
    if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
.venv\Scripts\python.exe manage.py migrate --noinput
if errorlevel 1 goto failed
.venv\Scripts\python.exe manage.py collectstatic --noinput
if errorlevel 1 goto failed
.venv\Scripts\python.exe manage.py check
if errorlevel 1 goto failed
echo.
echo Setup complete. Next: double-click create-teacher-windows.cmd
pause
exit /b 0
:failed
echo Setup failed. Keep this window open and ask for help.
pause
exit /b 1
