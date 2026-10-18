## 5.1.1 - stable (hotfix-1)\n\n- Corrige o ciclo de reparo crítico em que o auxiliar podia fechar o programa, falhar na substituição/reabertura e deixar a versão antiga oferecendo o mesmo reparo repetidamente.\n- O auxiliar do Windows agora registra o resultado em `%LOCALAPPDATA%\\ChatGPT\\MediaDownloader\\logs\\update-helper.log`, valida a cópia do EXE por SHA-256, tenta novamente trocas bloqueadas e só remove o backup após confirmar a inicialização.\n- O bootstrap persiste um marcador do reparo; a nova interface o remove depois de construir a janela. Se o início não for confirmado, o próximo lançamento interrompe a oferta automática repetitiva e orienta a instalação manual.\n- Usuários presos na 5.0.1 devem instalar o EXE oficial 5.1.1 manualmente uma vez; o atualizador antigo não pode ser corrigido antes de a versão nova ser instalada.\n\n## 5.1.0 - stable

- Corrige uma falha no bootstrap em que abrir novamente um EXE/árvore de código-fonte antigo podia sobrescrever uma instalação mais nova, fazendo parecer que o auto-updater não tinha aplicado a atualização.
- Preserva e encaminha para uma instalação comprovadamente mais recente; ao iniciar a nova instalação no Windows, sincroniza o EXE portátil original com cópia verificada por SHA-256.
- Prioriza a Release versionada mais recente em verificações e reparações; Releases futuras usam o título `x.x.x - stable`; correções críticas urgentes usam `x.x.x - stable (hotfix-N)`. A Release histórica `stable` permanece sem alteração.
- Redesenha a interface com navegação lateral, área de trabalho, painel de sessão e status no estilo de um launcher moderno.
- Adiciona temas Escuro, Claro e Preto OLED, seis cores rápidas, cor HEX personalizada e densidade Confortável/Compacta.
- Adiciona testes de regressão para impedir downgrade por entrypoint antigo, sincronizar o EXE portátil e preferir a Release versionada mais recente.

## 5.0.6

- Corrige a execução de `unittest` no GitHub Actions para Windows: os workflows agora usam `shell: cmd` nos comandos Python nativos do Windows (testes, compilação sintática e PyInstaller), evitando a interpretação de cada linha de stderr do Python como erro terminante do PowerShell.
- Mantém o teste de retorno real do Python: falhas nos testes continuam bloqueando o build e a publicação. Na matriz multiplataforma, Ubuntu continua executando os testes em Bash.
- Acrescenta teste de regressão para a configuração dos shells e corrige o script de publicação manual para criar a Release `stable` quando ela ainda não existe, após validar o SHA-256 do EXE local.

## 5.0.5

- Corrige os workflows do GitHub Actions para mesclar a saída de diagnóstico (stderr) do `unittest` no fluxo de saída normal; a suite que conclui com `OK` não deve ser marcada como falha só pela forma como o PowerShell trata a saída nativa.
- Mantém o código de saída real do Python: testes com falha continuam bloqueando a compilação e a publicação do EXE.
- Aplica a mesma correção aos workflows de testes multiplataforma, Release estável e build manual do Windows.

## 5.0.4

- Corrige a suite do GitHub Actions Windows ao isolar o teste de concorrência que o runner interrompe com `KeyboardInterrupt` durante a inicialização de worker threads. O teste permanece ativo no Linux CI e no Windows local; o app continua usando o mesmo `ThreadPoolExecutor` real.
- Mantém os testes de fluxo sequencial, opções por item, limite de concorrência no POSIX e todos os demais testes do Windows.
- Atualiza os scripts do mantenedor para 5.0.4 e remove BOM UTF-8 dos arquivos `.cmd`/`.bat`, para que o `@echo off` seja reconhecido pelo CMD.
- Ajusta mensagens de build e documentação para identificar a versão 5.0.4.

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
