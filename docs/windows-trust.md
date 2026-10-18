# Identificação do executável, SmartScreen e assinatura digital

## O que a versão 5.1.2 acrescenta

O arquivo `ChatGPTMediaDownloader.exe` contém um recurso de versão PE com o nome do produto, descrição, versão, copyright, nome original e URL do repositório. No Windows, essas informações aparecem em Propriedades → Detalhes e ajudam a reconhecer o arquivo.

**Essas informações não autenticam o publicador.** São metadados descritivos, não prova de identidade legal e não substituem uma assinatura Authenticode. O nome de fornecedor usado no recurso descreve os contribuidores do projeto de código aberto; não representa uma empresa registrada ou um editor certificado.

## Por que o Windows ainda pode avisar

O SmartScreen avalia reputação de arquivos e publicadores. Um aplicativo novo, especialmente se não assinado, pode ser sinalizado como desconhecido mesmo quando é publicado num repositório público. Atualizar a versão também muda o hash do arquivo, portanto os avisos podem reaparecer. Metadados PE e um checksum não garantem que o aviso desaparecerá.

Fontes oficiais:
- [Microsoft Learn — SmartScreen reputation for apps and files](https://learn.microsoft.com/windows/apps/package-and-deploy/smartscreen-reputation)
- [Microsoft — opções de assinatura de código para Windows](https://github.com/MicrosoftDocs/windows-dev-docs/blob/docs/hub/apps/package-and-deploy/code-signing-options.md)
- [PyInstaller — uso de recursos de versão](https://pyinstaller.org/en/stable/usage.html)

## Como é habilitada uma assinatura real

O workflow de publicação oferece assinatura Authenticode no runner Windows quando o mantenedor configura os secrets do repositório:
- `WINDOWS_SIGNING_CERT_BASE64`: certificado de assinatura de código válido no formato PFX, codificado em Base64.
- `WINDOWS_SIGNING_CERT_PASSWORD`: senha do arquivo PFX.

O workflow usa SignTool com SHA-256, timestamp e, em seguida, verifica a assinatura. O PFX não deve ser commitado no Git nem incluído em artefatos públicos. Uma cadeia de certificado confiável é necessária para uma identidade de editor verificada; o SmartScreen ainda pode avisar enquanto não houver reputação suficiente.

Na ausência desses secrets, a compilação não simula assinatura: publica `Windows-Signature-Status.txt` declarando que o executável está sem assinatura Authenticode. Essa é a situação atual até o mantenedor fornecer um certificado válido.

## Como obter o executável correto

1. Baixe o EXE apenas pela [Release oficial do repositório](https://github.com/slydtaz/Chatgpt-media-downloader/releases/latest).
2. Compare o SHA-256 do EXE com `SHA256SUMS.txt` da mesma Release e execute uma verificação com o Microsoft Defender.
3. Leia `Windows-Signature-Status.txt` para saber se houve assinatura e verificação Authenticode.
4. Não desative o antivírus, não instale certificados desconhecidos e não execute um arquivo apenas porque exibe um nome de empresa em Propriedades.

## Situação jurídica e identidade do projeto

Este é um projeto independente de código aberto distribuído sob a licença MIT; consulte o arquivo [LICENSE](../LICENSE). O aplicativo não é afiliado, patrocinado, certificado ou distribuído pela OpenAI. O copyright do recurso do executável identifica os contribuidores do projeto, e não afirma a existência de uma pessoa jurídica.
