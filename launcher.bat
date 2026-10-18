@echo off
setlocal
cd /d "%~dp0"
rem Bootstrap sem console: use launcher.vbs ou o atalho criado automaticamente.
where wscript.exe >nul 2>&1
if %errorlevel%==0 (
  wscript.exe //nologo "%~dp0launcher.vbs"
  exit /b 0
)
where pythonw.exe >nul 2>&1
if %errorlevel%==0 (
  start "" /b pythonw.exe -m app.bootstrap
  exit /b 0
)
where python.exe >nul 2>&1
if %errorlevel%==0 (
  start "" /b python.exe -m app.bootstrap
  exit /b 0
)
echo Python 3.11 ou superior nao foi encontrado.
pause
exit /b 1
