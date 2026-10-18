# Publicar a Release estável

A Release oficial para usuários finais utiliza a tag `stable` e precisa ter um título com a versão do aplicativo, por exemplo `ChatGPT Media Downloader 5.0.1 — Stable`. O atualizador lê a versão numérica do título quando a tag não é um número de versão.

## Publicação manual no Windows

1. Envie as alterações de `main` para o repositório.
2. Crie a tag `stable` sobre o commit de produção e envie-a: `git tag -a stable -m "ChatGPT Media Downloader 5.0.1 stable"` e `git push origin stable`. Não force nem mova uma tag estável publicada sem intenção explícita.
3. Em **GitHub → Releases → Draft a new release**, selecione a tag `stable` e nomeie a Release `ChatGPT Media Downloader 5.0.1 — Stable`. Marque como a Release mais recente (Latest).
4. Execute `CREATE_EXE_OWNER_ONLY.bat` no Windows e teste `dist\ChatGPTMediaDownloader.exe`.
5. Anexe `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt` à Release stable. O atualizador de executáveis exige ambos os arquivos e valida o SHA-256.
6. Na descrição da Release, indique que o EXE é recomendado para usuários finais e os fontes/ZIPs automáticos do GitHub são para desenvolvedores.

**Importante:** o título precisa conter a versão correta. Para versões futuras, atualize `app/config.py` e o título da Release juntos. O EXE e o hash devem ser do mesmo build testado.
