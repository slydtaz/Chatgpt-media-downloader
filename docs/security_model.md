# Modelo de segurança e limites

## Escopo e transparência

O Media Downloader é um projeto independente de código aberto. Ele não solicita privilégios de administrador para os downloads usuais, não incorpora cookies ou senhas por padrão e não foi projetado para contornar DRM, autenticação, paywalls ou controles de acesso.

Nenhum teste de unidade, hash de arquivo ou verificação automática prova que um programa é 100% seguro. Os controles descritos aqui reduzem riscos conhecidos, mas não substituem auditoria independente, monitoramento de vulnerabilidades nem análise do executável pelo antivírus do usuário.

## Controles no aplicativo

- As URLs de mídia aceitas usam HTTP ou HTTPS com autoridade válida; URLs com credenciais embutidas ou domínios malformados são rejeitadas.
- Processos externos recebem listas de argumentos, não comandos concatenados para um shell.
- Os logs removem caminhos de URL, query strings e padrões que aparentem conter credenciais.
- Os instaladores de dependências aceitam apenas hosts HTTPS explicitamente permitidos do GitHub, validam redirecionamentos, aplicam limites de tamanho e verificam SHA-256 quando o projeto de origem publica um manifesto. Um manifesto ausente ou inválido interrompe a instalação automática.
- Antes da extração, arquivos compactados têm seus caminhos validados; caminhos de travessia, links simbólicos e entradas especiais são rejeitados.
- As atualizações do aplicativo verificam o host final, tamanho, hash e identidade de produto esperada antes de substituir os arquivos existentes. Os dados pessoais de configuração e as mídias baixadas ficam separados da instalação.
- O download de playlists exige seleção dos itens disponíveis. O paralelismo tem limites explícitos e não habilita acesso a conteúdo privado.
- O binário é empacotado sem ofuscação deliberada. Metadados PE identificam o produto, mas não autenticam o publicador.

## Distribuição e verificação

1. Baixe o programa exclusivamente da página de Releases deste repositório.
2. Compare o SHA-256 do executável com `SHA256SUMS.txt` anexado à mesma versão. O hash detecta diferenças em relação a um valor confiável; isoladamente, não prova quem publicou o arquivo.
3. Leia `Windows-Signature-Status.txt` e verifique o arquivo com o Microsoft Defender ou outro antivírus.
4. Não desative o antivírus, não instale certificados desconhecidos e não execute cópias que venham de mirrors ou mensagens não oficiais.

O SHA-256 do build, testes e proveniência de CI ajudam a rastrear o arquivo gerado. Eles não substituem uma auditoria independente nem uma assinatura Authenticode confiável.

## Limite da assinatura do Windows

O workflow aceita assinatura Authenticode real quando o mantenedor configura um certificado de assinatura de código válido nos secrets `WINDOWS_SIGNING_CERT_BASE64` e `WINDOWS_SIGNING_CERT_PASSWORD`. Sem esse certificado, o executável continua **sem assinatura Authenticode** e o relatório publicado deve informar isso. Não serão usados nomes de empresa inventados, certificados próprios não confiáveis, metadados falsos ou técnicas para contornar o SmartScreen.

## Dependências de terceiros

O aplicativo usa yt-dlp, FFmpeg e FFprobe, que são projetos externos. A verificação de integridade depende dos metadados e dos manifestos fornecidos pelos respectivos projetos; quando esses dados não estão disponíveis ou não batem, o instalador automático falha fechado. Os binários têm licenças e ciclos de atualização próprios.

## Reportar uma vulnerabilidade

Não publique detalhes exploráveis, dados privados, tokens ou arquivos maliciosos em Issues públicos. Use o recurso privado de Security Advisory do GitHub, se estiver habilitado. Se não estiver, abra um issue genérico pedindo um canal privado, sem incluir o detalhe técnico da vulnerabilidade.

Veja também [SECURITY.md](../SECURITY.md) e [identificação/assinatura do Windows](windows-trust.md).
