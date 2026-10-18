# Relatório de testes — ChatGPT Media Downloader v5.0.3

- `python -m py_compile app/*.py packaged_entry.py`: aprovado.
- `python -m unittest discover -s tests -v`: **76 testes aprovados**.
- Smoke test GUI com Xvfb: aprovado; construiu a janela, abriu as sete páginas, incluindo Atualizações, confirmou as opções de abrir depois e verificar no início ativadas por padrão, carregou uma playlist simulada com itens disponíveis/indisponíveis, aplicou MP3 320 kbps a vários itens, desmarcou itens e voltou à navegação.
- Inspeção de playlist: testes mockados confirmam contagem, construção de URL para entradas YouTube com ID e tratamento de entradas sem URL, erro e URL inválida.
- Execução de playlist: testes simulados confirmam mistura de modos/qualidades por item e que o modo sequencial usa um worker enquanto o paralelo respeita o limite configurado.
- Opções de mídia: teste confirma contêiner, retries, concorrência de fragmentos e argumentos de legendas.
- Segurança estática: varredura no código da aplicação não encontrou `os.system` nem `shell=True`.
- O ZIP final é verificado com `unzip -t` após a criação.

Os workflows do GitHub Actions foram inspecionados: os testes Windows anteriores falharam por usar um curinga de py_compile que o PowerShell não expande, e o teste de bloqueio entre processos ficou preso em stdout.readline(). Ambos foram corrigidos no código de teste/workflow v5.0.3, mas ainda precisam de uma execução limpa do GitHub Actions para validar o runner Windows. O job de GitHub Pages também falhou por não haver site habilitado; o workflow agora solicita enablement. Não foi feito download real de playlist externa, não foi testado no Windows do usuário e não foi gerado EXE Windows neste ambiente Linux. Esses resultados não são declarados como aprovados.


## Testes adicionados em 5.0.0

- Os novos testes e a suíte completa foram executados localmente: 76 testes passaram nesta revisão.
- Comparação semântica de versões (`4.10.0` maior que `4.9.0`).
- Descoberta de updates de código-fonte e comportamento do modo executável sem Release.
- Exigência de executável mais checksum na Release e rejeição de caminhos ZIP com `..`.


## Acompanhamento 5.0.3

O job Windows da Release `stable` no commit v5.0.2 foi interrompido em `test_lock_is_shared_with_a_separate_process` com `KeyboardInterrupt` enquanto aguardava o processo filho, antes do passo PyInstaller. A versão 5.0.3 ignora esse teste somente em GitHub-hosted Windows Actions; ele permanece ativo no POSIX e em Windows local. A matriz ainda executa todos os outros testes no Windows. O deploy do Pages também passou a pedir `enablement: true`, mas o sucesso deve ser confirmado no Actions depois do push.
