# Publicar este pacote no GitHub

O pacote está pronto, mas ainda precisa ser enviado para um repositório hospedado na sua conta.

## 1. Criar o repositório remoto

1. Acesse https://github.com/new e crie o repositório `chatgpt-media-downloader`.
2. Marque **Public** se quiser disponibilizar publicamente Issues, Pull Requests, Releases e a página de downloads.
3. **Não marque** as opções para criar README, `.gitignore` ou licença: esses arquivos já estão neste pacote.
4. Copie a URL HTTPS do repositório. O endereço esperado para este projeto é `https://github.com/slydtaz/chatgpt-media-downloader.git`.

## 2. Enviar o código (terminal com Git instalado)

Extraia o ZIP, abra o terminal na pasta `chatgpt-media-downloader` e execute:

```bash
git init -b main
git add .
git commit -m "chore: import ChatGPT Media Downloader 5.0.0"
git remote add origin https://github.com/slydtaz/chatgpt-media-downloader.git
git push -u origin main
```

Se você criou o repositório com outro nome ou usuário, troque a URL do `origin`. O Git pode pedir autenticação pelo navegador ou por um gerenciador de credenciais; nunca coloque token de acesso diretamente neste arquivo ou em commits.

## 3. Ativar a página de download

No GitHub, abra **Settings → Pages**, selecione **GitHub Actions** como origem e salve. O workflow `.github/workflows/pages.yml` publica `site/index.html` quando `site/` muda e o commit é enviado para `main` ou `master`.

## 4. Criar a primeira release para Windows

Quando o código estiver no repositório, crie e envie uma tag de versão:

```bash
git tag v5.0.0
git push origin v5.0.0
```

O workflow de release executa os testes, tenta criar `ChatGPTMediaDownloader.exe` num runner Windows, calcula o SHA-256 e publica ambos os arquivos como assets da GitHub Release. Se a compilação falhar, nenhum asset válido deve ser anunciado como pronto para download; verifique **Actions** e corrija a causa antes de tentar novamente.

## Observação

O conector GitHub disponível nesta sessão não oferece a operação de criar repositórios novos. Por isso, este pacote e os passos acima preparam a publicação, mas não significam que um repositório remoto ou uma release já tenham sido criados.
