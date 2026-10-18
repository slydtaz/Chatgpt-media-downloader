# Matriz de preservação — BAT 3.9 → GUI 4.2

| Função existente do BAT | Preservada? | Implementação 4.2 |
|---|---|---|
| `APP_NAME=ChatGPT Media Downloader` | Sim | `app/config.py` |
| Vendor `ChatGPT` | Sim | `app/config.py` / tela Desenvolvedor |
| Product ID `com.chatgpt.mediadownloader` | Sim | `app/config.py` / tela Desenvolvedor |
| versão base 3.9-BAT | Evoluída | versão 4.2.0 |
| pasta de músicas padrão | Sim | `DEFAULT_MUSIC_DIR` |
| pasta de vídeos padrão | Sim | `DEFAULT_VIDEO_DIR` |
| caminhos manuais yt-dlp/FFmpeg/FFprobe | Sim | janela Configurações |
| APP_DATA em `%LOCALAPPDATA%` no Windows | Sim | `app/config.py` |
| `tools/`, `temp/`, `logs/` privados | Sim | `app/config.py` |
| criação de Install ID UUID | Sim | `ensure_install_id()` |
| defaults 1080p / 192 kbps | Sim | configuração inicial |
| detecção Windows x86/x64/ARM64 | Sim | `app/platform.py` |
| busca manual → app → PATH | Sim | `app/dependencies.py` |
| menu automático URL → vídeo | Sim | GUI, modo Automático — vídeo |
| vídeo 480p | Sim | seletor gráfico |
| vídeo 720p | Sim | seletor gráfico |
| vídeo 1080p | Sim | seletor gráfico |
| vídeo 1440p | Sim | seletor gráfico |
| vídeo 2160p / 4K | Sim | seletor gráfico |
| `--no-playlist` | Sim | downloader |
| `--check-formats` | Sim | downloader |
| merge em MP4 | Sim | downloader |
| 5 retries | Sim | downloader |
| 5 fragment retries | Sim | vídeo |
| 4 concurrent fragments | Sim | vídeo |
| FFmpeg via `--ffmpeg-location` | Sim | downloader |
| template `%title%.200B [id]` | Sim | downloader |
| MP3 128/192/320 | Sim | seletor gráfico |
| `--embed-metadata` | Sim | áudio |
| `--embed-thumbnail` | Sim | áudio |
| menu Configurações | Sim | janela Configurações |
| qualidade automática editável | Sim | janela Configurações |
| bitrate editável | Sim | janela Configurações |
| reencontrar ferramentas | Sim | Dependências |
| menu Dependências | Sim | janela Dependências |
| versões das ferramentas | Sim | inspeção real dos executáveis |
| arquitetura das ferramentas | Sim | análise PE/ELF + macOS conservadora |
| menu Ajuda | Sim | janela Ajuda |
| menu Desenvolvedor | Sim | janela Desenvolvedor |
| diretórios app/tools/logs/temp | Sim | app em instalação própria; logs/temp/config separados no perfil do usuário |
| desinstalação confirmada | Sim | diálogo + script separado |
| preservação dos downloads | Sim | desinstalador não toca nas pastas de download |
| não encerrar yt-dlp externo genérico | Sim | não usa taskkill genérico |
| saída do app no fim | Sim | encerramento da GUI |
| shell para o download | Corrigida/fortalecida | `subprocess` com lista de argumentos |
| URL passada como argumento | Sim | último argumento separado |
| ajuda sobre suporte do yt-dlp | Sim | janela Ajuda |
| warning sobre autenticação/site | Sim | janela Ajuda + mensagens de erro |
| atualização | Expandida | `app/updater.py` |
| arquitetura primeiro, versão depois | Expandida | seletor de asset compatível |
| checksum / validação | Nova proteção | SHA-256 + teste do executável |
| progresso real | Expandida | parsing da saída `--newline` do yt-dlp |
| cancelamento | Expandida | término do processo atual |
| logs sem credenciais | Expandida | redaction |
| segurança de arquivo | Expandida | sanitização + proteção de extração |
