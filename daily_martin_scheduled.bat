@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".local\logs" mkdir ".local\logs"
set "LOG=.local\logs\daily_martin.log"

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo [%date% %time%] Scheduled Martin Luk check start>> "%LOG%"
echo ==================================================>> "%LOG%"

call "%~dp0run_martin_daily.bat" >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo [%date% %time%] Martin Luk exit code: %RC%>> "%LOG%"
exit /b %RC%
