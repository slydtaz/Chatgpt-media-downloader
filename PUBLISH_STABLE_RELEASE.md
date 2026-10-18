# Publicar a Release estável

As Releases estáveis versionadas usam uma tag como `v5.1.0` e título `5.1.0 - stable`. Correções críticas que exigem atualização imediata usam `5.1.0 - stable (hotfix-1)`, com o número sequencial real. A primeira Release da tag `stable` é mantida sem alteração por compatibilidade.

## Publicação automatizada

1. Publique o código aprovado em `main` e confirme que os testes do GitHub Actions estão verdes.
2. Crie/envie uma tag de versão, por exemplo `v5.1.0`, apontando para o commit aprovado. O workflow `release.yml` é disparado por tags `v*` e cria a Release com o título `5.1.0 - stable`.
3. Para uma correção crítica urgente, use o `workflow_dispatch` e informe o número do hotfix; o título será `5.1.0 - stable (hotfix-1)`. Não informe número para uma release normal.
4. Não mova a tag histórica `stable`: ela permanece apontando para a primeira Release/alias e não dispara mais a publicação versionada. A nova Release inclui o EXE, `SHA256SUMS.txt` e `ChatGPTMediaDownloader-5.1.0-source.zip`.
5. Acompanhe [GitHub Actions](https://github.com/slydtaz/Chatgpt-media-downloader/actions). Considere a Release pronta apenas quando o workflow concluir com sucesso e os três arquivos aparecerem nos assets.

## Download de usuários e desenvolvedores

- **Usuários finais:** `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt` anexados à Release versionada mais recente.
- **Desenvolvedores:** ZIP do código-fonte ou `Code → Download ZIP`, para leitura, auditoria e compilação.

Se o workflow falhar, abra os logs da execução antes de fazer upload manual. O script `PUBLISH_EXE_TO_STABLE.bat` pode criar a Release versionada correspondente à versão se ela ainda não existir, desde que o EXE e o checksum tenham sido gerados e validados localmente no Windows. A compilação do EXE Windows precisa ocorrer no Windows; não publique um executável sem testá-lo e validar o SHA-256.
