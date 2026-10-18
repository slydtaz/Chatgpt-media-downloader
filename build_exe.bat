@echo off
chcp 65001 >nul
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Build ChatGPT Media Downloader - single EXE

echo ============================================================
echo   ChatGPT Media Downloader 5.0.4 - Build de arquivo unico
echo ============================================================
echo.

where py >nul 2>nul
if errorlevel 1 (
  echo ERRO: o Python Launcher ^(py.exe^) nao foi encontrado.
  echo Instale Python 3.11 ou superior em https://www.python.org/downloads/windows/
  echo Marque a opcao Python Launcher durante a instalacao.
  if not defined BUILD_NO_PAUSE pause
  exit /b 1
)

py -3 -c "import sys, tkinter; print('Python:', sys.version.split()[0]); print('Tkinter: OK')"
if errorlevel 1 (
  echo ERRO: Python 3 ou Tkinter nao esta disponivel.
  if not defined BUILD_NO_PAUSE pause
  exit /b 1
)

echo.
echo [1/3] Instalando/atualizando PyInstaller...
py -3 -m pip install --upgrade pyinstaller
if errorlevel 1 (
  echo ERRO: nao foi possivel instalar PyInstaller.
  if not defined BUILD_NO_PAUSE pause
  exit /b 1
)

echo.
echo [2/3] Compilando um unico executavel, sem console...
py -3 -m PyInstaller --noconfirm --clean ChatGPTMediaDownloader.spec
if errorlevel 1 (
  echo ERRO: a compilacao falhou. Consulte a mensagem acima.
  if not defined BUILD_NO_PAUSE pause
  exit /b 1
)

if not exist "dist\ChatGPTMediaDownloader.exe" (
  echo ERRO: o executavel nao foi encontrado em dist\.
  if not defined BUILD_NO_PAUSE pause
  exit /b 1
)

echo.
echo [3/3] Calculando SHA-256 para acompanhar o executavel...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -LiteralPath 'dist\ChatGPTMediaDownloader.exe' -Algorithm SHA256).Hash.ToLowerInvariant(); ($h + '  ChatGPTMediaDownloader.exe') | Set-Content -LiteralPath 'dist\SHA256SUMS.txt' -Encoding ascii"
if errorlevel 1 (
  echo AVISO: nao foi possivel criar dist\SHA256SUMS.txt.
) else (
  echo Hash criado: %CD%\dist\SHA256SUMS.txt
)

echo.
echo [FINAL] Build concluido.
echo Executavel: %CD%\dist\ChatGPTMediaDownloader.exe
echo.
echo Esse EXE e o unico arquivo que precisa ser distribuido inicialmente.
echo Na primeira execucao, ele instala-se por usuario/sistema e baixa yt-dlp e FFmpeg quando necessario.
echo Build log/EXE esperados nesta pasta: %CD%\dist
if not defined BUILD_NO_PAUSE pause
exit /b 0
