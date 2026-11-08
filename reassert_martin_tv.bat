@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM After First Screen, re-assert newest-dated Martin E_Main as active TV list.
set "YT=%~dp0"
set "SCR=%~dp0..\screening"
set "WL=%YT%outputs\watchlists"
set "NODE=node"
if not exist "%SCR%\scripts\tv_upload_watchlist.js" (
  echo [WARN] tv_upload_watchlist.js missing
  exit /b 0
)
if not exist "%WL%" (
  echo [WARN] no watchlists dir
  exit /b 0
)
set "LATEST="
for /f "delims=" %%F in ('dir /b /a-d "%WL%\Martin_Luk_*_E_Main.txt" 2^>nul ^| sort /R') do (
  set "LATEST=%WL%\%%F"
  goto :found
)
echo [WARN] no Martin_Luk_*_E_Main.txt
exit /b 0
:found
echo [%date% %time%] Re-assert Martin TV list: !LATEST!
"%NODE%" "%SCR%\scripts\tv_upload_watchlist.js" "!LATEST!"
exit /b %ERRORLEVEL%
