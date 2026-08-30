@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo Martin Luk is chained after 9edge-Daily-FirstScreen (no separate schedule).
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_daily_martin_task.ps1"
echo.
echo Optional: first push to GitHub (repo must exist: kinaoc-ui/youtube_summaries)
call "%~dp0push_summaries_git.bat" "Initial Martin Luk summaries"
pause
