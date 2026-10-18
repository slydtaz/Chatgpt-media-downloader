## 5.0.3

- Corrige o bloqueio da publicação de EXE causado pela execução interrompida do teste multiprocesso no runner Windows hospedado; o teste continua ativo no Linux e em execuções locais do Windows, e os demais testes de locking permanecem ativos em todas as plataformas.
- Solicita a habilitação do GitHub Pages por meio da ação oficial de configuração, além de usar o workflow para publicar a página.
- Mantém o build de Release condicionado a testes e a geração conjunta do EXE de arquivo único e de seu SHA-256.

## 5.0.2

- Corrige a detecção e publicação da tag `stable`: o publicador busca explicitamente a tag remota, compara o commit e pede confirmação antes de atualizá-la.
- Corrige a compilação sintática no CI do Windows, evitando curinga que o PowerShell não expande.
- Torna o teste de bloqueio entre processos limitado por tempo e com diagnóstico em Windows, evitando travamento de `stdout.readline()`.
- Faz a publicação da Release estável construir e anexar automaticamente o EXE único e seu SHA-256 no GitHub Actions.
- Prioriza a Release `stable` na busca por atualizações, mesmo quando uma Release sem assets aparece como `latest`.
- Solicita habilitação do GitHub Pages no workflow de deploy e melhora o diagnóstico dos scripts locais de build/upload.

## 5.0.1

- Atualiza `build_exe.bat` para calcular `SHA256SUMS.txt` depois da compilação, compatível com a validação do atualizador.
- Permite usar a tag-alias `stable` em Releases do GitHub quando o título informa a versão semântica.
- Atualiza a documentação para diferenciar o EXE recomendado para usuários do ZIP de código-fonte para desenvolvedores.

# Histórico de versões

## 5.0.0

- Atualizador do aplicativo integrado ao GitHub Releases e à versão da branch `main` para instalações em código-fonte.
- Confirmação antes de baixar, notas de versão e caixa "Abrir o aplicativo automaticamente depois de atualizar", ativada por padrão.
- Download para pasta de preparação, validação de checksum SHA-256 para builds EXE, extração ZIP segura e troca transacional com rollback.
- Reparo completo dos arquivos a partir de uma fonte oficial, incluindo oferta de recuperação após falha crítica na inicialização.
- Preferências e mídias baixadas permanecem fora da pasta do aplicativo e são preservadas durante a atualização.
- Novos testes automatizados de comparação de versões, descoberta de atualizações e validação de arquivos ZIP.

Consulte [`docs/5.0.0_changes.md`](docs/5.0.0_changes.md).

## 4.9.0

- Gerenciador de playlists com busca, seleção individual e configurações por item.
- Download de vídeo ou MP3 por entrada; modo sequencial ou paralelo limitado.
- Melhorias de logs, inicialização, atualização e preparação de dependências.
- Ver [`docs/4.9.0_changes.md`](docs/4.9.0_changes.md) para o histórico técnico detalhado.

Consulte `docs/` para notas de versões anteriores. Versões futuras serão registradas aqui.
