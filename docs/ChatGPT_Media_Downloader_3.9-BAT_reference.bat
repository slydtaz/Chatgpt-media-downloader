@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
mode con cols=104 lines=38 >nul 2>&1
title ChatGPT Media Downloader
color 0B

rem ================================================================
rem ChatGPT Media Downloader - latest reconstructed BAT
rem Vendor: ChatGPT
rem Product ID: com.chatgpt.mediadownloader
rem ================================================================

set "APP_NAME=ChatGPT Media Downloader"
set "PRODUCT_ID=com.chatgpt.mediadownloader"
set "VENDOR=ChatGPT"
set "VERSION=3.9-BAT"

rem User download folders
set "MUSIC_DIR=%USERPROFILE%\OneDrive\Desktop\musicas\Baixadas\Musicas"
set "VIDEO_DIR=%USERPROFILE%\OneDrive\Desktop\musicas\Baixadas\Videos"

rem Optional explicit tool paths. Leave blank for automatic detection.
set "YTDLP_PATH="
set "FFMPEG_PATH="
set "FFPROBE_PATH="

rem App-local directories
set "APP_DATA=%LOCALAPPDATA%\ChatGPT\MediaDownloader"
set "TOOLS_DIR=%APP_DATA%\tools"
set "TEMP_DIR=%APP_DATA%\temp"
set "LOG_DIR=%APP_DATA%\logs"
set "CONFIG=%APP_DATA%\config.bat"
set "INSTALL_ID_FILE=%APP_DATA%\install_id.txt"

call :bootstrap
call :loadConfig
call :detectArchitecture
call :findTools

goto :MENU

:bootstrap
if not exist "%APP_DATA%" md "%APP_DATA%" >nul 2>&1
if not exist "%TOOLS_DIR%" md "%TOOLS_DIR%" >nul 2>&1
if not exist "%TEMP_DIR%" md "%TEMP_DIR%" >nul 2>&1
if not exist "%LOG_DIR%" md "%LOG_DIR%" >nul 2>&1
if not exist "%APP_DATA%\config" md "%APP_DATA%\config" >nul 2>&1
if not exist "%INSTALL_ID_FILE%" (
    for /f "tokens=*" %%G in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString()" 2^>nul') do >"%INSTALL_ID_FILE%" echo %%G
)
exit /b

:loadConfig
if exist "%CONFIG%" call "%CONFIG%"
exit /b

:saveConfig
>"%CONFIG%" echo rem Generated configuration for %APP_NAME%
>>"%CONFIG%" echo set "MUSIC_DIR=%MUSIC_DIR%"
>>"%CONFIG%" echo set "VIDEO_DIR=%VIDEO_DIR%"
>>"%CONFIG%" echo set "AUTO_VIDEO_QUALITY=%AUTO_VIDEO_QUALITY%"
>>"%CONFIG%" echo set "AUDIO_BITRATE=%AUDIO_BITRATE%"
>>"%CONFIG%" echo set "YTDLP_PATH=%YTDLP_PATH%"
>>"%CONFIG%" echo set "FFMPEG_PATH=%FFMPEG_PATH%"
>>"%CONFIG%" echo set "FFPROBE_PATH=%FFPROBE_PATH%"
exit /b

:defaults
if not defined AUTO_VIDEO_QUALITY set "AUTO_VIDEO_QUALITY=1080"
if not defined AUDIO_BITRATE set "AUDIO_BITRATE=192"
if not defined MUSIC_DIR set "MUSIC_DIR=%USERPROFILE%\OneDrive\Desktop\musicas\Baixadas\Musicas"
if not defined VIDEO_DIR set "VIDEO_DIR=%USERPROFILE%\OneDrive\Desktop\musicas\Baixadas\Videos"
exit /b

:detectArchitecture
set "OS_ARCH=%PROCESSOR_ARCHITECTURE%"
if defined PROCESSOR_ARCHITEW6432 set "OS_ARCH=%PROCESSOR_ARCHITEW6432%"
if /I "%OS_ARCH%"=="AMD64" set "ARCH_LABEL=x64"
if /I "%OS_ARCH%"=="x86" set "ARCH_LABEL=x86"
if /I "%OS_ARCH%"=="ARM64" set "ARCH_LABEL=ARM64"
if not defined ARCH_LABEL set "ARCH_LABEL=%OS_ARCH%"
exit /b

:findTools
call :defaults

if defined YTDLP_PATH if exist "%YTDLP_PATH%" goto ytdlp_done
set "YTDLP_PATH="

if /I "%ARCH_LABEL%"=="x86" (
    if exist "%TOOLS_DIR%\yt-dlp_x86.exe" set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp_x86.exe"
) else if /I "%ARCH_LABEL%"=="ARM64" (
    if exist "%TOOLS_DIR%\yt-dlp_arm64.exe" set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp_arm64.exe"
) else (
    if exist "%TOOLS_DIR%\yt-dlp.exe" set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp.exe"
)

if not defined YTDLP_PATH (
    if exist "%TOOLS_DIR%\yt-dlp.exe" set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp.exe"
    if exist "%TOOLS_DIR%\yt-dlp_x86.exe" if not defined YTDLP_PATH set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp_x86.exe"
    if exist "%TOOLS_DIR%\yt-dlp_arm64.exe" if not defined YTDLP_PATH set "YTDLP_PATH=%TOOLS_DIR%\yt-dlp_arm64.exe"
)

if not defined YTDLP_PATH (
    for /f "delims=" %%G in ('where yt-dlp.exe 2^>nul') do if not defined YTDLP_PATH set "YTDLP_PATH=%%G"
    for /f "delims=" %%G in ('where yt-dlp 2^>nul') do if not defined YTDLP_PATH set "YTDLP_PATH=%%G"
)

ytdlp_done:
if defined FFMPEG_PATH if exist "%FFMPEG_PATH%" goto ffmpeg_done
set "FFMPEG_PATH="
if exist "%TOOLS_DIR%\ffmpeg.exe" set "FFMPEG_PATH=%TOOLS_DIR%\ffmpeg.exe"
if not defined FFMPEG_PATH for /f "delims=" %%G in ('where ffmpeg.exe 2^>nul') do if not defined FFMPEG_PATH set "FFMPEG_PATH=%%G"
if not defined FFMPEG_PATH for /f "delims=" %%G in ('where ffmpeg 2^>nul') do if not defined FFMPEG_PATH set "FFMPEG_PATH=%%G"

ffmpeg_done:
if defined FFPROBE_PATH if exist "%FFPROBE_PATH%" goto tools_done
set "FFPROBE_PATH="
if exist "%TOOLS_DIR%\ffprobe.exe" set "FFPROBE_PATH=%TOOLS_DIR%\ffprobe.exe"
if not defined FFPROBE_PATH for /f "delims=" %%G in ('where ffprobe.exe 2^>nul') do if not defined FFPROBE_PATH set "FFPROBE_PATH=%%G"
if not defined FFPROBE_PATH for /f "delims=" %%G in ('where ffprobe 2^>nul') do if not defined FFPROBE_PATH set "FFPROBE_PATH=%%G"

tools_done:
exit /b

:clear
cls
exit /b

:header
call :clear
for /f "delims=" %%G in ('powershell -NoProfile -Command "[char]0x2554 + ('='*68) + [char]0x2557"') do echo %%G
powershell -NoProfile -Command "Write-Host ('ChatGPT Media Downloader'.PadLeft(34).PadRight(68)) -ForegroundColor Cyan"
powershell -NoProfile -Command "Write-Host ('v%VERSION%'.PadLeft(31).PadRight(68)) -ForegroundColor DarkCyan"
for /f "delims=" %%G in ('powershell -NoProfile -Command "[char]0x255A + ('='*68) + [char]0x255D"') do echo %%G
echo.
exit /b

:MENU
call :header
call :defaults
call :findTools

echo   Sistema/arquitetura: %OS_ARCH% / %ARCH_LABEL%
echo   yt-dlp:   %YTDLP_PATH%
echo   FFmpeg:   %FFMPEG_PATH%
echo.
echo  [1] Baixar automaticamente (URL = video)
echo  [2] Baixar video
 echo  [3] Baixar musica (MP3)
echo  [4] Configuracoes
 echo  [5] Dependencias
 echo  [6] Ajuda
 echo  [7] Desenvolvedor
 echo  [8] Desinstalar
 echo  [9] Sair
 echo.
choice /c 123456789 /n /m "  Escolha: "
if errorlevel 9 goto :EXIT
if errorlevel 8 goto :UNINSTALL
if errorlevel 7 goto :DEVELOPER
if errorlevel 6 goto :HELP
if errorlevel 5 goto :DEPENDENCIES
if errorlevel 4 goto :SETTINGS
if errorlevel 3 goto :AUDIO_MENU
if errorlevel 2 goto :VIDEO_MENU
if errorlevel 1 goto :AUTO_DOWNLOAD
goto :MENU

:AUTO_DOWNLOAD
call :header
echo MODO AUTOMATICO - VIDEO
call :readURL
if not defined URL goto :MENU
call :downloadVideo %AUTO_VIDEO_QUALITY%
goto :MENU

:VIDEO_MENU
call :header
echo ESCOLHA A QUALIDADE DO VIDEO
 echo.
echo [1] 480p
 echo [2] 720p
 echo [3] 1080p
 echo [4] 1440p
 echo [5] 4K (2160p)
 echo [6] Voltar
 echo.
choice /c 123456 /n /m "  Escolha: "
if errorlevel 6 goto :MENU
if errorlevel 5 set "VIDEO_QUALITY=2160" & goto :VIDEO_URL
if errorlevel 4 set "VIDEO_QUALITY=1440" & goto :VIDEO_URL
if errorlevel 3 set "VIDEO_QUALITY=1080" & goto :VIDEO_URL
if errorlevel 2 set "VIDEO_QUALITY=720" & goto :VIDEO_URL
if errorlevel 1 set "VIDEO_QUALITY=480" & goto :VIDEO_URL
goto :VIDEO_MENU

:VIDEO_URL
call :header
echo VIDEO - %VIDEO_QUALITY%p
call :readURL
if not defined URL goto :MENU
call :downloadVideo %VIDEO_QUALITY%
goto :MENU

:AUDIO_MENU
call :header
echo ESCOLHA A QUALIDADE DO AUDIO
 echo.
echo [1] 128 kbps
 echo [2] 192 kbps
 echo [3] 320 kbps
 echo [4] Voltar
 echo.
choice /c 1234 /n /m "  Escolha: "
if errorlevel 4 goto :MENU
if errorlevel 3 set "AUDIO_QUALITY=320" & goto :AUDIO_URL
if errorlevel 2 set "AUDIO_QUALITY=192" & goto :AUDIO_URL
if errorlevel 1 set "AUDIO_QUALITY=128" & goto :AUDIO_URL
goto :AUDIO_MENU

:AUDIO_URL
call :header
echo AUDIO - %AUDIO_QUALITY% kbps
call :readURL
if not defined URL goto :MENU
call :downloadAudio %AUDIO_QUALITY%
goto :MENU

:readURL
set "URL="
echo.
set /p "URL=Cole a URL: "
if not defined URL exit /b
if /I not "%URL:~0,7%"=="http://" if /I not "%URL:~0,8%"=="https://" (
    echo.
    echo URL invalida. Use http:// ou https://
    pause
    set "URL="
)
exit /b

:checkTools
call :findTools
if not defined YTDLP_PATH (
    echo.
    echo [ERRO] yt-dlp nao foi encontrado.
    echo Use Configuracoes ^> Caminho do yt-dlp.
    pause
    exit /b 1
)
if not defined FFMPEG_PATH (
    echo.
    echo [ERRO] FFmpeg nao foi encontrado.
    echo Use Configuracoes ^> Caminho do FFmpeg.
    pause
    exit /b 1
)
exit /b 0

:downloadVideo
set "Q=%~1"
call :checkTools
if errorlevel 1 exit /b
if not exist "%VIDEO_DIR%" md "%VIDEO_DIR%" >nul 2>&1
call :header
echo Download de video: %Q%p
 echo Destino: %VIDEO_DIR%
echo.
"%YTDLP_PATH%" --newline --no-playlist --check-formats -f "bv*[height<=%Q%]+ba/b[height<=%Q%]/bv*+ba/b" --merge-output-format mp4 --retries 5 --fragment-retries 5 --concurrent-fragments 4 --ffmpeg-location "%FFMPEG_PATH%" -o "%VIDEO_DIR%\%%(title).200B [%%(id)s].%%(ext)s" "%URL%" >>"%LOG_DIR%\downloads.log" 2>&1
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo [OK] Download concluido.
    echo Se %Q%p nao existia, o seletor do yt-dlp tentou uma qualidade compativel disponivel.
) else (
    echo [ERRO] O yt-dlp terminou com codigo %RC%.
    echo Veja: %LOG_DIR%\downloads.log
)
echo.
pause
exit /b

:downloadAudio
set "B=%~1"
call :checkTools
if errorlevel 1 exit /b
if not exist "%MUSIC_DIR%" md "%MUSIC_DIR%" >nul 2>&1
call :header
echo Download de musica: %B% kbps
 echo Destino: %MUSIC_DIR%
echo.
"%YTDLP_PATH%" --newline --no-playlist -x --audio-format mp3 --audio-quality "%B%K" --embed-metadata --embed-thumbnail --ffmpeg-location "%FFMPEG_PATH%" -o "%MUSIC_DIR%\%%(title).200B [%%(id)s].%%(ext)s" "%URL%" >>"%LOG_DIR%\downloads.log" 2>&1
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo [OK] Musica concluida.
) else (
    echo [ERRO] O yt-dlp terminou com codigo %RC%.
    echo Veja: %LOG_DIR%\downloads.log
)
echo.
pause
exit /b

:DEPENDENCIES
call :header
echo DEPENDENCIAS
 echo.
echo Sistema: %OS_ARCH%
echo Arquitetura detectada: %ARCH_LABEL%
echo.
if defined YTDLP_PATH (
    echo [OK] yt-dlp: %YTDLP_PATH%
    "%YTDLP_PATH%" --version 2>nul
) else echo [X] yt-dlp: nao encontrado
echo.
if defined FFMPEG_PATH (
    echo [OK] FFmpeg: %FFMPEG_PATH%
    "%FFMPEG_PATH%" -version 2>nul | findstr /i "ffmpeg version" | findstr /v "configuration"
) else echo [X] FFmpeg: nao encontrado
echo.
if defined FFPROBE_PATH (
    echo [OK] FFprobe: %FFPROBE_PATH%
    "%FFPROBE_PATH%" -version 2>nul | findstr /i "ffprobe version"
) else echo [!] FFprobe: nao encontrado
 echo.
echo Regra: arquitetura compativel primeiro; versao mais nova depois.
pause
goto :MENU

:SETTINGS
call :header
echo CONFIGURACOES
 echo.
echo [1] Pasta de musicas
 echo [2] Pasta de videos
 echo [3] Qualidade automatica de video ^(%AUTO_VIDEO_QUALITY%p^)
 echo [4] Bitrate padrao de audio ^(%AUDIO_BITRATE% kbps^)
 echo [5] Caminho do yt-dlp
 echo [6] Caminho do FFmpeg
 echo [7] Caminho do FFprobe
 echo [8] Reencontrar ferramentas automaticamente
 echo [9] Voltar
 echo.
choice /c 123456789 /n /m "  Escolha: "
if errorlevel 9 goto :MENU
if errorlevel 8 call :findTools & pause & goto :SETTINGS
if errorlevel 7 goto :SET_FFPROBE
if errorlevel 6 goto :SET_FFMPEG
if errorlevel 5 goto :SET_YTDLP
if errorlevel 4 goto :SET_BITRATE
if errorlevel 3 goto :SET_AUTOQ
if errorlevel 2 goto :SET_VIDEODIR
if errorlevel 1 goto :SET_MUSICDIR
goto :SETTINGS

:SET_MUSICDIR
set "NEWPATH="
set /p "NEWPATH=Nova pasta de musicas: "
if defined NEWPATH set "MUSIC_DIR=%NEWPATH%"
call :saveConfig
pause
goto :SETTINGS

:SET_VIDEODIR
set "NEWPATH="
set /p "NEWPATH=Nova pasta de videos: "
if defined NEWPATH set "VIDEO_DIR=%NEWPATH%"
call :saveConfig
pause
goto :SETTINGS

:SET_AUTOQ
set /p "NEWQ=Nova qualidade automatica (480/720/1080/1440/2160): "
if "%NEWQ%"=="480" set "AUTO_VIDEO_QUALITY=480"
if "%NEWQ%"=="720" set "AUTO_VIDEO_QUALITY=720"
if "%NEWQ%"=="1080" set "AUTO_VIDEO_QUALITY=1080"
if "%NEWQ%"=="1440" set "AUTO_VIDEO_QUALITY=1440"
if "%NEWQ%"=="2160" set "AUTO_VIDEO_QUALITY=2160"
call :saveConfig
pause
goto :SETTINGS

:SET_BITRATE
set /p "NEWB=Novo bitrate (128/192/320): "
if "%NEWB%"=="128" set "AUDIO_BITRATE=128"
if "%NEWB%"=="192" set "AUDIO_BITRATE=192"
if "%NEWB%"=="320" set "AUDIO_BITRATE=320"
call :saveConfig
pause
goto :SETTINGS

:SET_YTDLP
set /p "YTDLP_PATH=Digite o caminho completo do yt-dlp: "
call :saveConfig
call :findTools
pause
goto :SETTINGS

:SET_FFMPEG
set /p "FFMPEG_PATH=Digite o caminho completo do FFmpeg: "
call :saveConfig
call :findTools
pause
goto :SETTINGS

:SET_FFPROBE
set /p "FFPROBE_PATH=Digite o caminho completo do FFprobe: "
call :saveConfig
call :findTools
pause
goto :SETTINGS

:HELP
call :header
echo AJUDA
 echo.
echo Automatico: cole uma URL e o programa baixa como video.
echo Video: 480p, 720p, 1080p, 1440p e 4K.
echo Musica: MP3 em 128, 192 ou 320 kbps.
echo.
echo Se a resolucao pedida nao existir, o seletor tenta um formato compativel.
echo O resultado real depende dos formatos oferecidos pelo site.
echo.
echo O mecanismo de sites e fornecido principalmente pelo yt-dlp.
echo Isso pode incluir YouTube, TikTok, Instagram, X/Twitter, Reddit, Vimeo e outros,
echo mas sites podem exigir login ou mudar o funcionamento.
echo.
echo Downloads nao sao apagados pela opcao de desinstalacao.
echo Apenas arquivos da aplicacao, configuracao e temporarios gerenciados sao removidos.
echo.
pause
goto :MENU

:DEVELOPER
call :header
echo DESENVOLVEDOR
 echo.
echo Vendor: %VENDOR%
echo Product ID: %PRODUCT_ID%
echo Version: %VERSION%
echo Architecture: %ARCH_LABEL%
echo Install ID:
if exist "%INSTALL_ID_FILE%" type "%INSTALL_ID_FILE%"
echo.
echo App data: %APP_DATA%
echo Tools: %TOOLS_DIR%
echo Logs: %LOG_DIR%
echo Temp: %TEMP_DIR%
echo.
echo O programa executa localmente yt-dlp e FFmpeg via subprocess.
echo Nao usa shell para montar comandos a partir da URL.
echo O URL e passado como argumento ao yt-dlp.
echo.
echo Este BAT e uma versao de desenvolvimento/reconstruida e nao e um instalador
 echo digitalmente assinado.
echo.
pause
goto :MENU

:UNINSTALL
call :header
echo DESINSTALACAO
 echo.
echo Isto remove somente arquivos da aplicacao em:
echo %APP_DATA%
echo.
echo Suas musicas e videos em:
echo %MUSIC_DIR%
echo %VIDEO_DIR%
echo NAO serao apagados.
echo.
echo Escreva DESINSTALAR para continuar.
set /p "CONFIRM=> "
if /I not "%CONFIRM%"=="DESINSTALAR" goto :MENU

rem Nao encerra qualquer yt-dlp do sistema, pois isso poderia afetar outro programa.
rem O usuario deve encerrar downloads ativos antes da desinstalacao.
if exist "%APP_DATA%" rmdir /s /q "%APP_DATA%" >nul 2>&1

echo.
echo Arquivos da aplicacao removidos, quando permitido.
echo O BAT atual nao sera apagado automaticamente para evitar apagar um arquivo
 echo que possa estar sendo executado de outra pasta.
echo.
pause
goto :EXIT

:EXIT
endlocal
exit /b 0
