@echo off
setlocal EnableExtensions
REM After First Screen, re-assert the latest *complete dated* Martin E_Main
REM as the active TradingView list.
REM   name:  Martin_Luk_YYYY-MM-DD_E_Main.txt
REM   body:  ###INDEXES ###LONGS ###SHORTS ###FOCUS  (TRACKING optional)
REM The date in the filename wins. Mtime, reverse-alpha sort, NA / undated
REM names, video-id copies, and TRACKING-only files are never uploaded.
cd /d "%~dp0"

if not defined TUBEON_TV_UPLOAD set "TUBEON_TV_UPLOAD=1"
if not defined TUBEON_TV_SCREENING_ROOT set "TUBEON_TV_SCREENING_ROOT=%~dp0..\screening"
if not defined TUBEON_TV_CDP_PORT set "TUBEON_TV_CDP_PORT=9222"
if not defined TUBEON_TV_AUTO_LAUNCH set "TUBEON_TV_AUTO_LAUNCH=1"

set "PYTHON_EXE="
where py >nul 2>&1 && set "PYTHON_EXE=py"
if not defined PYTHON_EXE (
  where python >nul 2>&1 && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
  if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  )
)
if not defined PYTHON_EXE (
  echo [ERROR] Python not found. Martin Active was not changed.
  exit /b 1
)

echo [%date% %time%] Re-assert latest complete dated Martin E_Main
"%PYTHON_EXE%" "%~dp0scripts\reassert_martin_tv.py" %*
exit /b %ERRORLEVEL%
