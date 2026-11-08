@echo off
REM One-command: extract Leader/screener list from iMBI3ZcQ6sU → TradingView .txt
REM Run from repo root (Luk checkout): C:\Users\kinao\OneDrive\桌面\stock\youtube
setlocal EnableExtensions
cd /d "%~dp0"

set "PYTHON_EXE="
where py >nul 2>&1 && set "PYTHON_EXE=py"
if not defined PYTHON_EXE (
  where python >nul 2>&1 && set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
  echo [ERROR] Python not found.
  exit /b 1
)

echo [%date% %time%] E_Main sidebar OCR+vision: iMBI3ZcQ6sU
echo Tip: set TUBEON_OPENAI_API_KEY for vision E_Main sidebar read
echo Watchlist name / CDP listStem: Martin_Luk_2026-10-28_E_Main
echo.
echo Optional CDP upload into TV Desktop (keeps ### sections):
echo   1^) set TUBEON_TV_UPLOAD=1
echo   2^) set TUBEON_TV_SCREENING_ROOT=C:\Users\kinao\OneDrive\桌面\stock\screening
echo   3^) run launch_tv_debug.bat  OR  set TUBEON_TV_AUTO_LAUNCH=1
echo   watchlist_job will then call: node scripts\tv_upload_watchlist.js ^<abs Martin_Luk_*.txt^>
echo   ^(martin_daily needs no separate upload — it kicks watchlist_job^)
echo.
"%PYTHON_EXE%" "%~dp0scripts\watchlist_job.py" iMBI3ZcQ6sU --mode auto --force --vision --upload-date 20261028 %*
set "RC=%ERRORLEVEL%"
if %RC% NEQ 0 (
  echo Falling back to cached-frames / screenshot reparse...
  "%PYTHON_EXE%" "%~dp0scripts\watchlist_from_frames.py" iMBI3ZcQ6sU --frame watchlist-frames\e_main_sidebar.png --vision --upload-date 20261028
  set "RC=%ERRORLEVEL%"
)
echo.
echo Outputs:
echo   outputs\watchlists\iMBI3ZcQ6sU.txt
echo   outputs\watchlists\Martin_Luk_2026-10-28_E_Main.txt
echo   outputs\watchlists\iMBI3ZcQ6sU.md
echo   data\summaries\iMBI3ZcQ6sU.watchlist.json
echo [%date% %time%] exit %RC%
exit /b %RC%
