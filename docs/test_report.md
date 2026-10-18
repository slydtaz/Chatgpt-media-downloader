# Relatório de testes — ChatGPT Media Downloader v5.0.0

- `python -m py_compile app/*.py packaged_entry.py`: aprovado.
- `python -m unittest discover -s tests -v`: **70 testes aprovados**.
- Smoke test GUI com Xvfb: aprovado; construiu a janela, abriu as sete páginas, incluindo Atualizações, confirmou as opções de abrir depois e verificar no início ativadas por padrão, carregou uma playlist simulada com itens disponíveis/indisponíveis, aplicou MP3 320 kbps a vários itens, desmarcou itens e voltou à navegação.
- Inspeção de playlist: testes mockados confirmam contagem, construção de URL para entradas YouTube com ID e tratamento de entradas sem URL, erro e URL inválida.
- Execução de playlist: testes simulados confirmam mistura de modos/qualidades por item e que o modo sequencial usa um worker enquanto o paralelo respeita o limite configurado.
- Opções de mídia: teste confirma contêiner, retries, concorrência de fragmentos e argumentos de legendas.
- Segurança estática: varredura no código da aplicação não encontrou `os.system` nem `shell=True`.
- O ZIP final é verificado com `unzip -t` após a criação.

Não foi feito download real de playlist externa, não foi testado no Windows do usuário e não foi gerado EXE Windows neste ambiente Linux. Esses resultados não são declarados como aprovados.


## Testes adicionados em 5.0.0

- Os novos testes e a suíte completa foram executados localmente: 70 testes passaram nesta revisão.
- Comparação semântica de versões (`4.10.0` maior que `4.9.0`).
- Descoberta de updates de código-fonte e comportamento do modo executável sem Release.
- Exigência de executável mais checksum na Release e rejeição de caminhos ZIP com `..`.
