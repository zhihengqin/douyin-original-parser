@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Project Python was not found in .venv\Scripts\python.exe
    pause
    exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\compare_original_sessions.py" --show-verified-url %*
set "SESSION_COMPARE_EXIT=%ERRORLEVEL%"
if /I not "%~1"=="--help" pause
exit /b %SESSION_COMPARE_EXIT%
