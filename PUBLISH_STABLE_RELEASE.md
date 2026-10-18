# Publicar a Release estável

A Release oficial usa a tag `stable` e o título inclui a versão real, por exemplo `ChatGPT Media Downloader 5.0.5 — Stable`.

## Publicação automatizada

1. Execute `EXECUTAR_PUBLICACAO.cmd` no pacote do mantenedor. O script publica o código em `main`, consulta a tag remota `stable` em uma referência temporária e compara o commit real.
2. Se `main` tiver mudanças novas, o script pede confirmação antes de atualizar a tag `stable`. Não confirma se não desejar publicar esses arquivos como estáveis.
3. O envio da tag `stable` dispara `.github/workflows/release.yml` em um runner Windows. O workflow executa a compilação e os testes, gera o EXE único e o `SHA256SUMS.txt` e cria/atualiza a Release `stable`.
4. Acompanhe [GitHub Actions](https://github.com/slydtaz/Chatgpt-media-downloader/actions). A Release só estará pronta quando o workflow concluir com sucesso e anexar ambos os arquivos.

## Download de usuários e desenvolvedores

- **Usuários finais:** `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt` anexados à Release `stable`.
- **Desenvolvedores:** ZIP do código-fonte ou `Code → Download ZIP`, para leitura, auditoria e compilação.

Se o workflow falhar, abra os logs da execução antes de fazer upload manual. A compilação do EXE Windows precisa ocorrer no Windows; não publique um executável sem testá-lo e validar o SHA-256.
