<div align="center">

# ChatGPT Media Downloader

**Aplicativo desktop para baixar vídeos e músicas e administrar playlists com uma interface gráfica.**

[Baixar a versão mais recente](https://github.com/slydtaz/chatgpt-media-downloader/releases/latest) ·
[Reportar um erro](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=bug_report.yml) ·
[Sugerir uma melhoria](https://github.com/slydtaz/chatgpt-media-downloader/issues/new?template=feature_request.yml)

![Sistema: Windows](https://img.shields.io/badge/SO-Windows-0078D6)
![Versão-fonte](https://img.shields.io/badge/vers%C3%A3o-fonte%205.4.0--beta.3-orange)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

</div>

> **Segurança:** o projeto não foi desenvolvido para conter vírus e, até o momento, não há malware intencional conhecido no código-fonte. Isso não equivale a uma certificação independente nem permite garantir que todo executável gerado esteja 100% livre de vírus ou de falsos positivos. Baixe somente nas **releases deste repositório**, verifique o SHA-256 publicado e faça a verificação com o antivírus do seu sistema.

> **Aviso de nome:** “ChatGPT” no nome é apenas parte do identificador do projeto. Este software é independente e **não é afiliado, patrocinado, certificado ou distribuído pela OpenAI**.

> **UI customizada 5.4.0-beta.3:** gradiente neon animado, correção dos cantos dos botões, tela orbital de carregamento e seletor de versões no atualizador. Esta beta também mantém o relatório do VirusTotal para o executável, desinstalador, ZIP do código-fonte e as versões exatas de `yt-dlp`, `ffmpeg.exe` e `ffprobe.exe` verificadas pelo aplicativo.
>
> **Pré-release para avaliação:** a beta poderá ser publicada com detecções explícitas, desde que todos os scans terminem e o relatório completo seja anexado. Leia `VirusTotal-Status.txt` antes de executar qualquer binário. Uma publicação beta não significa que a versão foi aprovada como estável; a pipeline estável continua exigindo assinatura Authenticode confiável e ausência de detecções.

## 🎨 Aparência e personalização

A interface customizada combina fundos cósmicos com acentos violeta, azul, ciano e verde-menta. Os botões compatíveis apresentam dois contornos em gradientes distintos e preenchimento que acompanha a fase das bordas ao passar o cursor. A animação só fica ativa quando habilitada em Configurações; caso contrário, o estado de hover é estático e leve. Personalize os temas **Escuro**, **Claro** e **Preto OLED**, cores, densidade e modo de desenvolvedor.

Ao colar uma URL pública de vídeo ou áudio, a prévia aparece automaticamente após uma breve pausa e mostra capa, título, canal e duração quando disponíveis. Essa etapa consulta somente metadados com `yt-dlp` e busca apenas a imagem da capa, nunca o arquivo de vídeo/áudio. O gerenciador de playlists também exibe miniaturas nos itens. Se o site bloquear metadados ou não fornecer capa, o app mantém um painel de fallback e informa a indisponibilidade sem interromper o download.

## 🛡️ Proteção de downloads e análise de segurança

A base de segurança valida os destinos de redirecionamento HTTPS, limita tamanhos, restringe a extração de arquivos compactados e confere SHA-256 para dependências. Esta beta também corrige a classificação de domínios usados no fallback de miniaturas. Essas proteções reduzem riscos conhecidos, mas não equivalem a auditoria independente.

A pipeline de distribuição inclui análise CodeQL e envia ao VirusTotal seis amostras públicas: aplicativo, desinstalador, ZIP do código-fonte e os binários exatos de `yt-dlp`, FFmpeg e FFprobe usados pelo app. O relatório lista hashes, resultados por mecanismo e links de cada arquivo. Os envios entram no conjunto de dados compartilhado do VirusTotal; nenhum arquivo confidencial deve ser enviado. A beta pode incluir detecções para investigação e pode ficar sem assinatura Authenticode, mas as releases estáveis continuam bloqueadas até que todos os scans estejam completos e limpos e o executável tenha assinatura confiável. Nunca desative o antivírus para executar o aplicativo.

## 🔎 Integridade e proveniência

Os builds de release incluem `SHA256SUMS.txt` e o relatório explícito de assinatura do Windows. A pipeline também gera uma atestação de proveniência da GitHub Actions para os artefatos publicados; desenvolvedores podem conferi-la com o GitHub CLI usando `gh attestation verify` e o repositório de origem. A atestação ajuda a vincular o artefato ao processo de build, mas **não equivale à assinatura Authenticode do executável** nem a uma auditoria independente.

A página hospedada de downloads só é publicada quando GitHub Pages estiver habilitado em **Settings → Pages** e a variável de repositório `PUBLISH_GITHUB_PAGES` for definida como `true`. Até lá, use diretamente a página de Releases oficial.

## 📥 Download oficial para usuários

**Uso normal:** abra **[Releases estáveis — baixar](https://github.com/slydtaz/chatgpt-media-downloader/releases/latest)** e baixe `ChatGPTMediaDownloader.exe`. Confira o `SHA256SUMS.txt` da mesma Release. Para testar esta versão, use a **pré-release beta 5.4.0-beta.3** somente depois que a publicação aparecer na aba Releases; leia primeiro `VirusTotal-Status.txt` e verifique `SHA256SUMS.txt`. Não confunda artefatos de CI com um instalador oficial. **Desinstalador emergencial:** baixe `GPT-Media-Uninstaller.exe` da release correspondente.

1. Baixe `ChatGPTMediaDownloader.exe` da Release estável.
2. (Recomendado) Compare o SHA-256 do arquivo com `SHA256SUMS.txt` da mesma Release.
3. Faça uma verificação com o Microsoft Defender ou seu antivírus antes de executar.
4. Abra o EXE. Na primeira execução, o aplicativo prepara suas dependências de mídia (yt-dlp/FFmpeg) a partir de releases oficiais configurados no projeto, conferindo o manifesto SHA-256 quando publicado pela origem.

**Se o reparo continuar falhando:** baixe uma vez o EXE da [última Release oficial](https://github.com/slydtaz/Chatgpt-media-downloader/releases/latest) e execute-o. A partir desta versão, a instalação no Windows prioriza uma pasta por usuário para evitar bloqueios de escrita em Program Files, e a recuperação após erro crítico oferece reparar, desinstalar ou cancelar. Consulte [a documentação de identificação e assinatura do Windows](docs/windows-trust.md).

## 🧑‍💻 Código-fonte para desenvolvedores

O ZIP de código-fonte da Release e o botão **Code → Download ZIP** são destinados a desenvolvedores, auditoria, testes e compilação. Usuários comuns não precisam baixar nem extrair o fonte: basta o EXE oficial. O GitHub também pode mostrar seus ZIP/TAR automáticos de código-fonte em cada Release.

**A atualização automática do executável depende de uma Release estável com `ChatGPTMediaDownloader.exe` e `SHA256SUMS.txt`.** A versão de código-fonte também pode identificar uma versão mais nova na branch `main`. A publicação de uma versão estável cria uma Release versionada com título no formato `x.x.x - stable`, compila o EXE e anexa `SHA256SUMS.txt`. A Release histórica sob a tag `stable` permanece como compatibilidade; o atualizador prioriza a versão estável versionada mais recente. Acompanhe a execução na aba Actions; não publique o EXE antes de o build terminar com sucesso.

## ✨ O que o programa faz

- Baixa vídeos em resoluções selecionáveis, incluindo até 4K quando a fonte oferece esse formato.
- Converte/baixa áudio como MP3 em bitrates configuráveis.
- Analisa playlists antes do download, exibe os itens detectados e permite escolher individualmente quais baixar.
- Permite definir modo e qualidade por item de playlist; pode processar itens em sequência ou paralelamente (limite configurável de até seis workers).
- Incorpora metadados e capas quando as ferramentas de origem e o formato suportam.
- Oferece telas para configurações, dependências, atualizações, ajuda e diagnóstico.
- Verifica novas versões no GitHub; antes de baixar, pede confirmação e oferece a opção de abrir o aplicativo após a troca (ativada por padrão).
- Atualiza o executável inteiro com validação SHA-256, ou substitui o pacote-fonte completo; preserva preferências, ferramentas e mídias baixadas.
- Inclui reparo da instalação a partir do pacote oficial do GitHub, também disponível quando a inicialização falha de forma crítica, com opção de desinstalar ou cancelar; inclui um desinstalador que valida a propriedade das pastas antes de removê-las.
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

- [Versão 5.2.0 — tema espacial, botões e console](docs/5.2.0_changes.md) · [Hotfix 5.1.5 — correção de inicialização e desinstalador](docs/5.1.5_changes.md) · [Hotfix 5.1.4 — diagnóstico de inicialização](docs/5.1.4_changes.md) · [Hotfix 5.1.3 — janela vazia, animações e interface](docs/5.1.3_changes.md) · [Hotfix 5.1.2 — recuperação, desinstalação e identificação Windows](docs/5.1.2_changes.md) · [Identificação, SmartScreen e assinatura digital](docs/windows-trust.md) · [Hotfix 5.1.1 — ciclo de reparo e reinicialização](docs/5.1.1_changes.md) · [Versão 5.1.0](docs/5.1.0_changes.md) · [Versão 5.0.6](docs/5.0.6_changes.md) · [Versão 5.0.5](docs/5.0.5_changes.md) · [Versão 5.0.4](docs/5.0.4_changes.md) · [Versão 5.0.3](docs/5.0.3_changes.md) · [Versão 5.0.2](docs/5.0.2_changes.md) · [Versão 5.0.1](docs/5.0.1_changes.md) · [Versão 5.0.0](docs/5.0.0_changes.md)
- [Matriz de funcionalidades legadas](docs/legacy_functionality_matrix.md)
- [Modelo de segurança e limites](docs/security_model.md)
- [Relatório de testes e limitações](docs/test_report.md)

## ⚠️ Uso responsável e legal

Você é responsável por respeitar direitos autorais, termos de serviço, privacidade e leis aplicáveis ao usar este aplicativo. Baixe apenas conteúdo que você tem autorização para salvar. Este projeto não incentiva acesso não autorizado, distribuição de conteúdo protegido ou violação de restrições.

## 📜 Licença

Este repositório é distribuído sob a licença MIT; consulte [`LICENSE`](LICENSE). Ferramentas de terceiros, como yt-dlp e FFmpeg, mantêm suas próprias licenças e termos.


## Avisos de segurança do Windows (beta)

Os executáveis beta incluem ícone e metadados de versão para identificar o produto nas propriedades do arquivo. **Isso não é uma assinatura digital.** Sem um certificado Authenticode confiável, o Windows ainda pode mostrar “Editor desconhecido”, exibir o SmartScreen ou bloquear a execução por Smart App Control/política corporativa. Não existe um ajuste de metadados capaz de remover legitimamente esses avisos. A assinatura confiável exige certificado de uma autoridade reconhecida ou distribuição aprovada pela Microsoft Store; mesmo assinados, novos aplicativos podem precisar construir reputação.

Antes de executar, baixe apenas da página oficial de Releases, confira os hashes em `SHA256SUMS.txt` e leia `VirusTotal-Status.txt`. Os relatórios desta beta podem conter detecções; não as considere falsos positivos sem investigação independente.
