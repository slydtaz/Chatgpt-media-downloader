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
