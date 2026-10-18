@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build ChatGPT Media Downloader - single EXE

echo ============================================================
echo   ChatGPT Media Downloader 5.0.0 - Build de arquivo unico
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERRO: o Python Launcher ^(py.exe^) nao foi encontrado.
  echo Instale Python 3.11 ou superior em https://www.python.org/downloads/windows/
  echo Marque a opcao Python Launcher durante a instalacao.
  pause
  exit /b 1
)

py -3 -c "import sys, tkinter; print('Python:', sys.version.split()[0]); print('Tkinter: OK')"
if errorlevel 1 (
  echo ERRO: Python 3 ou Tkinter nao esta disponivel.
  pause
  exit /b 1
)

echo.
echo [1/3] Instalando/atualizando PyInstaller...
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo ERRO: nao foi possivel instalar PyInstaller.
  pause
  exit /b 1
)

echo.
echo [2/3] Compilando um unico executavel, sem console...
py -3 -m PyInstaller --noconfirm --clean ChatGPTMediaDownloader.spec
if errorlevel 1 (
  echo ERRO: a compilacao falhou. Consulte a mensagem acima.
  pause
  exit /b 1
)

if not exist "dist\ChatGPTMediaDownloader.exe" (
  echo ERRO: o executavel nao foi encontrado em dist\.
  pause
  exit /b 1
)

echo.
echo [3/3] Build concluido.
echo Executavel: %CD%\dist\ChatGPTMediaDownloader.exe
echo.
echo Esse EXE e o unico arquivo que precisa ser distribuido inicialmente.
echo Na primeira execucao, ele instala-se por usuario/sistema e baixa yt-dlp e FFmpeg quando necessario.
start "" explorer.exe "%CD%\dist"
pause
exit /b 0
