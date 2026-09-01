@echo off
setlocal EnableExtensions
cd /d "%~dp0"

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
  echo [ERROR] Python not found.
  exit /b 1
)

if exist "C:\Program Files\Git\cmd" set "PATH=C:\Program Files\Git\cmd;%PATH%"

echo [%date% %time%] Martin Luk daily check...
"%PYTHON_EXE%" "%~dp0scripts\martin_daily.py" %*
set "RC=%ERRORLEVEL%"
echo [%date% %time%] exit %RC%
exit /b %RC%
