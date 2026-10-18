# Fontes externas usadas na implementação

As URLs de atualização não foram inventadas a partir de mirrors desconhecidos. O código consulta as APIs de release dos projetos e seleciona assets publicados pelos repositórios usados no projeto.

## yt-dlp

Repositório oficial:
https://github.com/yt-dlp/yt-dlp

O README do projeto lista os binários:

- `yt-dlp.exe` para Windows x64;
- `yt-dlp_x86.exe` para Windows 32-bit;
- `yt-dlp_arm64.exe` para Windows ARM64;
- `yt-dlp_linux` para Linux x86_64;
- `yt-dlp_linux_aarch64` para Linux ARM64;
- `yt-dlp_linux_armv7l.zip` para Linux ARMv7;
- `yt-dlp_macos` para macOS universal.

O updater usa:
`https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest`

e escolhe o asset por sistema/arquitetura.

## FFmpeg

Página de downloads:
https://ffmpeg.org/download.html

O projeto FFmpeg informa que distribui o código-fonte e aponta provedores de binários compilados, incluindo gyan.dev e BtbN.

O updater usa os releases do BtbN para builds estáticas compatíveis de Windows x64/ARM64 e Linux x64/ARM64:

`https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest`

A seleção é feita pelo nome do asset e o manifesto de checksums da própria release é usado quando disponível.

## Observação sobre macOS e Windows x86

Não é tratado como válido baixar um binário de outra arquitetura apenas porque ele é mais novo. Quando a fonte conhecida não publica um asset automático compatível, a GUI informa a necessidade de caminho manual em vez de instalar um binário incompatível.

## Incorporação de thumbnails em vídeo

O aplicativo usa os parâmetros oficiais do yt-dlp `--embed-thumbnail` (incorporar a thumbnail como capa) e `--embed-metadata`. Não usa `--write-thumbnail`, para que a imagem de trabalho não seja deixada como um arquivo lateral.

- Opções oficiais de yt-dlp: https://github.com/yt-dlp/yt-dlp/blob/master/README.md#post-processing-options
- Implementação atual do postprocessador e limpeza da imagem temporária: https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/postprocessor/embedthumbnail.py
- Opção de remux: https://github.com/yt-dlp/yt-dlp/blob/master/README.md#post-processing-options
