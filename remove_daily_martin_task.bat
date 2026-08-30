@echo off
setlocal EnableExtensions
echo Martin Luk has no separate Task Scheduler entry anymore.
echo It runs inside: 9edge-Daily-FirstScreen → daily_fs_scheduled.bat
echo.
echo To stop Martin Luk only: edit screening\daily_fs_scheduled.bat and remove the Martin block.
schtasks /Delete /TN "9edge-Daily-MartinLuk" /F 2>nul
echo Done.
pause
