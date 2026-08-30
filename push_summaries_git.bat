@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "GIT=C:\Program Files\Git\cmd\git.exe"
if not exist "%GIT%" set "GIT=git"

if not exist ".git" (
  echo [..] Init git repo → kinaoc-ui/youtube_summaries
  "%GIT%" init
  "%GIT%" branch -M main
  "%GIT%" remote remove origin 2>nul
  "%GIT%" remote add origin https://github.com/kinaoc-ui/youtube_summaries.git
)

echo [..] git add summaries / outputs / app...
"%GIT%" add -A
"%GIT%" status -sb

"%GIT%" diff --cached --quiet
if %ERRORLEVEL% equ 0 (
  echo [OK] Nothing to commit.
  exit /b 0
)

set "MSG=%~1"
if "%MSG%"=="" set "MSG=Update Martin Luk summaries %date% %time%"

"%GIT%" commit -m "%MSG%"
if errorlevel 1 (
  echo [ERROR] commit failed
  exit /b 1
)

echo [..] git push origin main...
"%GIT%" push -u origin main
if errorlevel 1 (
  echo [ERROR] push failed — create https://github.com/kinaoc-ui/youtube_summaries if missing, then login Git.
  exit /b 1
)

echo [OK] Pushed to github.com/kinaoc-ui/youtube_summaries
exit /b 0
