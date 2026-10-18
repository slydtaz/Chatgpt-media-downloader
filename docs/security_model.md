# Modelo de segurança e limites

Este aplicativo faz download de mídia de sites que o yt-dlp suporta. Não é possível afirmar que software é “100% seguro” ou que passe em todos os antivírus, então a distribuição deve informar o que foi testado e evitar truques para mascarar o binário.

## Proteções implementadas

- Aceita URL HTTP/HTTPS e usa listas de argumentos em vez de construir comandos de shell.
- Os logs redigem URLs completas e tokens/query parameters que aparentam ser sensíveis.
- A análise de playlist usa `--flat-playlist` e não salva/usa cookies ou senhas automaticamente.
- Itens sem URL de destino verificável não são selecionados.
- O modo paralelo tem limite explícito de até seis workers e confirmação para o usuário.
- yt-dlp/FFmpeg continuam sendo dependências externas e devem ser obtidos de fontes compatíveis/selecionadas pelo projeto.
- Não executa bypass de DRM, autenticação, paywall ou conteúdo privado.
- O empacotamento está em `console=False`, sem ofuscação deliberada de código. O EXE inclui metadados PE de versão e identificação, que são descritivos e podem ser alterados; eles não provam quem publicou o arquivo.

## Recomendações de release

- Construir o EXE num runner Windows limpo a partir do fonte revisado.
- Usar versão fixa do PyInstaller durante releases reproduzíveis.
- Executar análise estática, testes e um antivírus/EDR no artefato resultante.
- Publicar SHA-256 e, quando a distribuição for pública, assinar digitalmente com certificado de editor confiável. O workflow suporta Authenticode por certificado PFX fornecido como secrets `WINDOWS_SIGNING_CERT_BASE64` e `WINDOWS_SIGNING_CERT_PASSWORD`; sem esses secrets, o build é explicitamente marcado como não assinado.\n- Não afirmar que metadados PE ou o SHA-256 identificam um editor legalmente verificado; o SHA-256 detecta alteração apenas quando comparado com um valor confiável.\n- Consultar [`windows-trust.md`](windows-trust.md) para detalhes do SmartScreen, assinatura e cadeia de distribuição.
- Investigar falsos positivos com o fornecedor de antivírus. Não alterar o programa para tentar contornar a detecção.
- Atualizar yt-dlp/FFmpeg apenas de assets oficiais/verificados e validar arquitetura e checksum quando a origem publicar um.
