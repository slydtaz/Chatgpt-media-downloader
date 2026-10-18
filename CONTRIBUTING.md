# Contribuindo

Obrigado por considerar contribuir com o ChatGPT Media Downloader!

## Antes de começar

1. Abra um issue primeiro para bugs importantes ou mudanças grandes, para discutir o escopo.
2. Não abra issues públicas para vulnerabilidades; siga [`SECURITY.md`](SECURITY.md).
3. Nunca inclua senhas, cookies, tokens, URLs privadas, logs com dados pessoais ou arquivos baixados de terceiros.

## Fluxo sugerido

1. Faça fork do repositório e crie uma branch com nome claro, por exemplo `fix/playlist-timeout` ou `feature/export-history`.
2. Mantenha mudanças focadas e compatíveis com Python 3.10+.
3. Acrescente/atualize testes quando alterar comportamento.
4. Antes de abrir PR, execute:

   ```bash
   python -m py_compile app/*.py packaged_entry.py
   python -m unittest discover -s tests -v
   ```

5. Envie o PR para `main`, explique o problema, a solução, como testar e limitações conhecidas. Inclua capturas de tela se houver mudanças visuais, sem expor informações pessoais.

## Padrões para mudanças

- Prefira operações de subprocesso com listas de argumentos; não use `shell=True` sem uma justificativa de segurança revisada.
- Trate entradas externas e falhas de rede como não confiáveis.
- Não adicione telemetria, rastreamento, cookies ou coleta de dados sem discussão e consentimento explícitos.
- Não oculte comportamento do executável nem introduza técnicas para evitar antivírus.
- Atualizações de yt-dlp/FFmpeg devem usar fontes verificáveis e considerar hash, arquitetura e validação do executável.
- Preserve logs úteis sem incluir tokens ou dados sensíveis.

Ao abrir o Pull Request, confirme que você tem direito de contribuir com o código submetido e que aceita a licença do projeto.
