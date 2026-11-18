# Smoke HTTP/MCP instalado preparado

Estado: **PREPARED / NOT_RUN**. Aguardar SOURCE_READY do Root e READY de um novo candidato instalado 0.3.7. Nenhum prefixo anterior será reinstalado. `plan.json` deixa os bindings ausentes deliberadamente; não é autorização para executar um candidato anterior.

O smoke existente `scripts/live_client.py` foi lido integralmente. Ele usa o SDK MCP e HTTP real com duas identidades sintéticas, provisioning canônico, presença, eventos, mensagens, handoff, artefato e shared.md. Não chama um harness nem modelo. Sua saída esperada é `LIVE E2E RESULT: PASS`, acompanhada de código zero e cleanup próprio confirmado. Isso não qualifica aplicação de resposta nativa, browser, AT, humano ou cenários L.

Antes da execução futura, vincular Python/wheel/READY e verificar versão 0.3.7, origens dos três pacotes sob esse prefixo e bytes instalados. Conferir o SHA do script registrado no plano. O processo será `-I -B`, fora do checkout, com CWD e TMP próprios e irmãos. O ambiente do **processo pai do script**, antes do provisioning, também precisa ser sanitizado: não basta a sanitização que o próprio script aplica ao Server filho. Usar allowlist de variáveis do Windows, HOME/USERPROFILE/APPDATA/LOCALAPPDATA/TEMP/TMP próprios, PATH vazio e `PYTHONDONTWRITEBYTECODE=1`; não herdar variáveis de provider, credenciais, proxies, PYTHONPATH ou configurações OKTO/NEXUS. Nenhum arquivo de conta pessoal será aberto.

Executar uma única vez o argv do plano após esses gates, com observador de prazo externo de 180 s e inventário de processos próprios por nascimento e caminho. Capturar stdout/stderr sanitizados, hashes antes/depois, origens e retornos. O script cria seu próprio home/projeto temporário, faz stop canônico e exige saída física antes da remoção protegida. Se houver timeout ou cleanup incompleto, preservar dados e registrar NOT_GREEN; conter somente processos próprios comprovados, sem concluir ausência de todos os filhos com base em uma amostra curta. Não haverá retry automático nem fallback.

Esta preparação não criou home de serviço, sessão, processo de Server, usuário sintético, grant ou chamada MCP. O comando ainda não foi executado.
