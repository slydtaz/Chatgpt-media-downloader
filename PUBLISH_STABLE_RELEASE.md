# Publicar a Release estável

As Releases estáveis versionadas usam uma tag como `v5.1.0` e título `5.1.0 - stable`. Correções críticas que exigem atualização imediata usam `5.1.0 - stable (hotfix-1)`, com o número sequencial real. A primeira Release da tag `stable` é mantida sem alteração por compatibilidade.

## Publicação automatizada

1. Execute `EXECUTAR_PUBLICACAO.cmd` no pacote do mantenedor. O script publica o código em `main`, consulta a tag remota `stable` em uma referência temporária e compara o commit real.
2. Se `main` tiver mudanças novas, o script pede confirmação antes de atualizar a tag `stable`. Não confirma se não desejar publicar esses arquivos como estáveis.
3. O envio da tag `stable` dispara `.github/workflows/release.yml` em um runner Windows. O workflow executa testes, compila o EXE e gera `SHA256SUMS.txt`, publicando uma Release versionada (`v5.1.0`, título `5.1.0 - stable`) sem sobrescrever a Release histórica sob a tag `stable`.
4. Acompanhe [GitHub Actions](https://github.com/slydtaz/Chatgpt-media-downloader/actions). A Release só estará pronta quando o workflow concluir com sucesso e anexar ambos os arquivos.

## Download de usuários e desenvolvedores

- **Usuários finais:** `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt` anexados à Release versionada mais recente.
- **Desenvolvedores:** ZIP do código-fonte ou `Code → Download ZIP`, para leitura, auditoria e compilação.

Se o workflow falhar, abra os logs da execução antes de fazer upload manual. O script `PUBLISH_EXE_TO_STABLE.bat` pode criar a Release versionada correspondente à versão se ela ainda não existir, desde que o EXE e o checksum tenham sido gerados e validados localmente no Windows. A compilação do EXE Windows precisa ocorrer no Windows; não publique um executável sem testá-lo e validar o SHA-256.
