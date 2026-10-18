<div align="center">

# ChatGPT Media Downloader

**Aplicativo desktop para baixar vídeos e músicas e administrar playlists com uma interface gráfica.**

[Baixar a versão mais recente](https://github.com/slydtaz/chatgpt-media-downloader/releases/latest) ·
[Reportar um erro](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=bug_report.yml) ·
[Sugerir uma melhoria](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=feature_request.yml)

![Sistema: Windows](https://img.shields.io/badge/SO-Windows-0078D6)
![Versão-fonte](https://img.shields.io/badge/vers%C3%A3o-fonte%205.0.0-blue)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

</div>

> **Segurança:** o projeto não foi desenvolvido para conter vírus e, até o momento, não há malware intencional conhecido no código-fonte. Isso não equivale a uma certificação independente nem permite garantir que todo executável gerado esteja 100% livre de vírus ou de falsos positivos. Baixe somente nas **releases deste repositório**, verifique o SHA-256 publicado e faça a verificação com o antivírus do seu sistema.

> **Aviso de nome:** “ChatGPT” no nome é apenas parte do identificador do projeto. Este software é independente e **não é afiliado, patrocinado, certificado ou distribuído pela OpenAI**.

## 📥 Download oficial para usuários

**Recomendado:** abra **[Releases estáveis — baixar](https://github.com/slydtaz/chatgpt-media-downloader/releases/tag/stable)** e baixe `ChatGPTMediaDownloader.exe`. Esse é o pacote de um único arquivo para quem só quer instalar e usar o programa; confira também `SHA256SUMS.txt` da mesma Release.

1. Baixe `ChatGPTMediaDownloader.exe` da Release estável.
2. (Recomendado) Compare o SHA-256 do arquivo com `SHA256SUMS.txt` da mesma Release.
3. Faça uma verificação com o Microsoft Defender ou seu antivírus antes de executar.
4. Abra o EXE. Na primeira execução, o aplicativo prepara suas dependências de mídia (yt-dlp/FFmpeg) a partir de fontes configuradas no projeto.

## 🧑‍💻 Código-fonte para desenvolvedores

O ZIP de código-fonte da Release e o botão **Code → Download ZIP** são destinados a desenvolvedores, auditoria, testes e compilação. Usuários comuns não precisam baixar nem extrair o fonte: basta o EXE oficial. O GitHub também pode mostrar seus ZIP/TAR automáticos de código-fonte em cada Release.

**A atualização automática do executável depende de uma Release estável com `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt`.** A versão de código-fonte também pode identificar uma versão mais nova na branch `main`. Para compilar/publicar o executável, envie a tag `v5.0.0` e aguarde o workflow de Windows concluir com sucesso. Enquanto isso, use as instruções para executar a partir do código-fonte abaixo.

## ✨ O que o programa faz

- Baixa vídeos em resoluções selecionáveis, incluindo até 4K quando a fonte oferece esse formato.
- Converte/baixa áudio como MP3 em bitrates configuráveis.
- Analisa playlists antes do download, exibe os itens detectados e permite escolher individualmente quais baixar.
- Permite definir modo e qualidade por item de playlist; pode processar itens em sequência ou paralelamente (limite configurável de até seis workers).
- Incorpora metadados e capas quando as ferramentas de origem e o formato suportam.
- Oferece telas para configurações, dependências, atualizações, ajuda e diagnóstico.
- Verifica novas versões no GitHub; antes de baixar, pede confirmação e oferece a opção de abrir o aplicativo após a troca (ativada por padrão).
- Atualiza o executável inteiro com validação SHA-256, ou substitui o pacote-fonte completo; preserva preferências, ferramentas e mídias baixadas.
- Inclui reparo da instalação a partir do pacote oficial do GitHub, também disponível quando a inicialização falha de forma crítica.
- Mantém logs, configuração e ferramentas baixadas em diretórios de dados do usuário, separados dos arquivos de mídia.

Disponibilidade de qualidade, metadados e capas depende do site, do conteúdo, do formato e das dependências externas.

## 🖥️ Como executar pelo código-fonte

### Windows

1. Instale Python 3.11 ou superior com **Tkinter** disponível.
2. Baixe o ZIP do código pelo botão **Code → Download ZIP** ou clone o repositório.
3. Extraia o projeto numa pasta de trabalho.
4. Execute `launcher.vbs` para iniciar sem janela de console auxiliar. Para depuração, execute `launcher.bat`.

Para compilar no Windows, execute `build_exe.bat` na raiz do projeto, ao lado de `launcher.vbs`. Ele gera o arquivo único `dist\ChatGPTMediaDownloader.exe` e o arquivo `dist\SHA256SUMS.txt`, que deve acompanhar o EXE na Release. A compilação deve ser feita em Windows; PyInstaller não produz de forma suportada um EXE Windows a partir de Linux.

### Linux / macOS

Instale Python 3.10+ e Tkinter (em algumas distribuições Linux, o Tkinter é um pacote separado). Na raiz do projeto, execute:

```bash
chmod +x launcher.sh
./launcher.sh
```

Se sua distribuição não executar o script pelo Python, use `chmod +x launcher.sh` e `./launcher.sh`. A geração de um pacote nativo para macOS ainda requer empacotamento adicional e testes nesse sistema.

## 🔧 Dependências de mídia

O aplicativo prepara **yt-dlp**, **FFmpeg** e **FFprobe** conforme as funções solicitadas. Esses componentes são projetos de terceiros, atualizados independentemente e sujeitos às próprias licenças e condições. O aplicativo não incorpora senhas ou cookies por padrão e não deve ser usado para contornar DRM, autenticação, paywalls ou controles de acesso.

Fontes e detalhes: [`docs/official_sources.md`](docs/official_sources.md) e [`docs/security_model.md`](docs/security_model.md).

## 🧑‍💻 Desenvolvimento e testes

Requisitos: Python 3.10+; Tkinter para executar a interface. Não há dependências Python de terceiros obrigatórias para o núcleo.

```bash
python -m py_compile app/*.py packaged_entry.py
python -m unittest discover -s tests -v
```

A integração contínua executa estes testes no Windows e no Linux. Testes automatizados, isoladamente, não comprovam que todos os downloads reais funcionam em todos os sites.

## 🐛 Encontrou um problema?

Antes de abrir um relato, confira os problemas já abertos e a página de ajuda:

- **[Reportar erro (Bug report)](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=bug_report.yml)** — informe versão, Windows/ambiente, passos para reproduzir e mensagens do log. Remova tokens, cookies, URLs privadas e outros dados pessoais dos logs antes de compartilhar.
- **[Pedir melhoria (Feature request)](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=feature_request.yml)** — explique o problema que a sugestão resolveria e o comportamento esperado.
- **[Ver todos os Issues](https://github.com/slydtaz/chatgpt-media-downloader/issues)** — acompanhar bugs, dúvidas técnicas e propostas.

Não publique vulnerabilidades ou dados secretos em uma issue pública. Leia [`SECURITY.md`](SECURITY.md) para reportes de segurança.

## 🔀 Contribuir com Pull Requests

Contribuições são bem-vindas. Leia [`CONTRIBUTING.md`](CONTRIBUTING.md), abra uma branch para sua mudança, execute os testes e envie um **Pull Request** descrevendo o motivo, as alterações e como foram validadas. O formulário de PR do GitHub contém uma checklist.

## 📚 Documentação

- [Histórico de mudanças da versão 5.0.1](docs/5.0.1_changes.md) · [Versão 5.0.0](docs/5.0.0_changes.md)
- [Matriz de funcionalidades legadas](docs/legacy_functionality_matrix.md)
- [Modelo de segurança e limites](docs/security_model.md)
- [Relatório de testes e limitações](docs/test_report.md)

## ⚠️ Uso responsável e legal

Você é responsável por respeitar direitos autorais, termos de serviço, privacidade e leis aplicáveis ao usar este aplicativo. Baixe apenas conteúdo que você tem autorização para salvar. Este projeto não incentiva acesso não autorizado, distribuição de conteúdo protegido ou violação de restrições.

## 📜 Licença

Este repositório é distribuído sob a licença MIT; consulte [`LICENSE`](LICENSE). Ferramentas de terceiros, como yt-dlp e FFmpeg, mantêm suas próprias licenças e termos.
