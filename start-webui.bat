@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === Local TubeonAI WebUI ===
echo Folder: %CD%
echo.

REM Free port 8765 if something is already listening
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
  echo Stopping old process on 8765: PID %%P
  taskkill /F /PID %%P >nul 2>&1
)

echo Starting uvicorn on http://127.0.0.1:8765 ...
echo Keep this window open. Press Ctrl+C to stop.
echo.

start "" "http://127.0.0.1:8765"

python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
if errorlevel 1 (
  echo.
  echo Failed to start. Is Python installed / in PATH?
  pause
)
