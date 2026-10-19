## 5.3.2 - stable

- Replaces the blue-gray default interface with a cosmic violet/magenta/cyan palette and a larger, locally drawn Media Lab orbital mark.
- Renders navigation icons from 4× supersampled vector artwork when Pillow is available; keeps a native Tk vector fallback.
- Adds a debounced automatic media preview on supported public media URLs. yt-dlp reads metadata with skip-download enabled; the preview never downloads video/audio.
- Displays thumbnail previews in playlist entries and loads image data asynchronously with size limits, HTTPS requirements, public-host checks, and validated redirects.
- Bundles Pillow into the Windows EXE build and automatically captures a preview of the new panel during the UI screenshot workflow. The capture uses a local offline demo and starts no media downloads.
- Migrates the built-in accent color to violet while preserving user-defined accent colors and other preferences.

## 5.3.1 - stable

- Valida cada destino HTTPS de redirecionamento antes de enviar a próxima requisição nos downloads de atualizações e dependências; bloqueia downgrade para HTTP, userinfo, portas não padrão e hosts fora da lista permitida.
- Valida metadados de assets do GitHub antes do download, exige tamanho positivo/compatível e mantém a exigência de SHA-256 para dependências.
- Instala ferramentas extraídas por substituição atômica, sem gravar através de links simbólicos preexistentes; acrescenta testes para redirecionamentos e destinos de escrita inseguros.
- Acrescenta análise estática CodeQL e um fluxo de análise VirusTotal para executáveis públicos; a publicação fica bloqueada enquanto a assinatura Authenticode confiável ou os relatórios de antivírus não satisfizerem os requisitos.
- A assinatura ainda depende de certificado de código confiável e os testes/relatórios não tornam o programa invulnerável nem garantem zero alertas de antivírus.

## 5.3.0 - stable

- Reforça a validação de URLs, a redação de credenciais nos logs e a confiança nos destinos de download.
- Protege a extração ZIP/TAR contra travessia de caminhos, links simbólicos, entradas especiais e arquivos compactados desproporcionais.
- Valida origem, redirecionamentos, limite de tamanho e SHA-256 de yt-dlp/FFmpeg; ausência de manifesto válido interrompe instalação automática.
- Fixa actions da pipeline por SHA completo, fixa versões de build, reduz permissões de job e acrescenta proveniência verificável da GitHub Actions.
- Padroniza a interface em azul e cinza, usa botões sólidos e inicia novas instalações sem animações, preservando preferências e cores personalizadas existentes.
- Substitui a marca visual semelhante a terceiros por um símbolo próprio de download, para deixar clara a identidade independente do projeto.
- Documenta os limites de confiança: hashes e atestações não substituem assinatura Authenticode nem auditoria independente.
## 5.2.0 - stable

- Substitui o bloco com estrela da marca por uma imagem PNG estática e transparente com o símbolo branco, pequenas estrelas e nuvem azul; a arte fica embutida no código e funciona offline.
- Arredonda os cartões principais e introduz botões em rosa-violeta com brilho e destaque ao passar o cursor, mantendo os controles e comandos existentes.
- Troca a barra lateral por navegação compacta por ícones e dicas de contexto; melhora as transições entre páginas e permite desativar os movimentos nas Configurações.
- Simplifica o painel de atividade por padrão. A saída bruta de yt-dlp/FFmpeg e detalhes extensos passam a ficar sob o **Modo desenvolvedor**, configurável e persistente.
- Acrescenta a opção de reduzir/desativar movimento, testes da nova paleta e dos cantos arredondados, e captura automatizada de todas as abas em uma janela Windows real.
- Mantém compatibilidade com configurações antigas: as novas opções recebem valores padrão quando ainda não existem no perfil.

## 5.1.5 - stable (hotfix-5)

- Corrige a falha de inicialização: _strategy_label era chamado como método de instância, mas não aceitava o argumento implícito self. Agora o formatador é um método estático e tem teste de regressão.
- Acrescenta smoke test ao EXE empacotado: abre a janela real da interface, verifica o desenho da animação orbital e navega por todas as páginas, sem baixar mídia, verificar atualizações ou instalar dependências.
- Acrescenta GPT Media Uninstaller como executável independente, com remoção dos dados e instalações do aplicativo, identificação de cópias antigas/incompletas, remoção de atalhos e relatório de erros.
- O desinstalador preserva músicas e vídeos por padrão; a exclusão de pastas de saída exige opção explícita e confirmação digitada. Cópias portáteis/fonte também são opcionais.
- Publica o hash SHA-256 do EXE principal e do desinstalador na mesma lista de somas.

## 5.1.4 - stable (hotfix-4)

- Adiciona diagnóstico de reserva no ponto de entrada do EXE para registrar falhas que ocorrem antes do logger principal e mostrar uma mensagem nativa do Windows em exceções inesperadas.
- Salva os diagnósticos em `startup-fallback.log` no diretório de dados do usuário, com fallback para TEMP quando necessário.
- Adiciona testes para inicialização bem-sucedida, exceções inesperadas e fallback do arquivo de log.
- Não presume a causa exata do encerramento observado: o objetivo é tornar o erro visível e capturável para uma correção direcionada.

## 5.1.3 - stable (hotfix-3)

- Corrige a janela azul-escura vazia durante o início: a janela Tk fica oculta enquanto todos os componentes são construídos e só aparece após a interface estar pronta.
- Se a construção da interface falhar, a janela parcial é destruída, a exceção é registrada em app.log e o erro volta ao bootstrap em vez de deixar uma janela sem conteúdo aberta.
- Adiciona transições curtas entre páginas e uma animação leve de órbitas/partículas violeta no painel inicial, desenhada em Canvas sem dependências gráficas adicionais.
- Refina a composição da tela inicial com arte animada discreta, mantendo o foco em link, formato, progresso e histórico.
- Base visual inspirada em convenções gerais do SKlauncher 4.0 Beta (tema cósmico escuro e realces violeta), sem reutilizar marca, ícones ou recursos proprietários.

## 5.1.2 - stable (hotfix-2)

- A tela de falha crítica agora oferece opções explícitas para tentar reparar, desinstalar ou cancelar; uma tentativa fracassada já não impede o usuário de abrir esse menu outra vez.
- O instalador do executável prefere uma pasta por usuário no Windows, reduzindo falhas de atualização causadas por permissões insuficientes em Program Files.
- Adiciona botão de desinstalação nas configurações e rotina de limpeza que verifica o marcador do produto antes de remover arquivos; pastas de músicas/vídeos baixados não são removidas.
- Incorpora metadados de versão PE (versão, nome, descrição, copyright e link do repositório) e documenta que esses campos não substituem uma assinatura digital.
- O workflow oferece assinatura Authenticode e verificação quando certificados confiáveis forem configurados por secrets do repositório; sem certificado, a Release declara explicitamente que o EXE não está assinado.

## 5.1.1 - stable (hotfix-1)

- Corrige o ciclo de reparo crítico em que o auxiliar podia fechar o programa, falhar na substituição/reabertura e deixar a versão antiga oferecendo o mesmo reparo repetidamente.
- O auxiliar do Windows agora registra o resultado em `%LOCALAPPDATA%/ChatGPT/MediaDownloader/logs/update-helper.log`, valida a cópia do EXE por SHA-256, tenta novamente trocas bloqueadas e só remove o backup após confirmar a inicialização.
- O bootstrap persiste um marcador do reparo; a nova interface o remove depois de construir a janela. Se o início não for confirmado, o próximo lançamento interrompe a oferta automática repetitiva e orienta a instalação manual.
- Usuários presos na 5.0.1 devem instalar o EXE oficial 5.1.1 manualmente uma vez; o atualizador antigo não pode ser corrigido antes de a versão nova ser instalada.

## 5.1.0 - stable

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
