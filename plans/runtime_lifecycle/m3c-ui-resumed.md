# M3c — Retomada após saída não identificada

Em 2026-10-16, ao retornar do terminal histórico para o Meta-harness, a UI
exibia Reconnecting/Failed to fetch. Não havia listener em 8202 nem os PIDs
44320/44180 da geração 68. O último access log é de 20:58:19 UTC; stderr não
registra shutdown normal nem traceback. A consulta de Application Error/Windows
Error Reporting na janela próxima não trouxe registro. **A causa e o autor do
encerramento não foram estabelecidos**; não foi atribuída a outro agente nem
declarada corrigida. Os logs foram preservados antes da nova inicialização em
`build/runtime-lifecycle-m3c-live/unexpected-exit/`.

A mesma instalação global M3c foi iniciada sem mudar configuração ou journals.
Geração 69: launcher 35864, server 18616; HTTP pronto 21:22:58 UTC. Codex READY
21:23:04, Claude 21:23:08 e Pi 21:24:38. Quatro containers retidos do Pi tiveram
prova CONTAINER_STOPPED e reconciliação automática. Não houve confirmação manual
de término ou repetição de comandos. Agents exibiu os três locais online.

O pool Pi estava 0/5 com alvo 4 e backoff automático até 21:29:15. Uma mensagem
privada foi enviada **uma vez pela interface** às 21:28:30, antes desse prazo:
`NEXUS_M3C_RESUMED_PI_OK`. O runtime ficou pronto 21:29:01, iniciou o turno
21:29:02 e terminou 21:29:09. A UI mostrou resposta exata, 1/1 ACK e sessão
one-shot CLOSED (`ses_94d086175a25b09b51da05770684dd9e`), com 21 eventos.
Nenhuma ferramenta, leitura de arquivos ou tarefa adicional foi solicitada.

O atendimento sob demanda não aguardou o backoff de aquecimento. Quatro novas
aberturas de reposição foram admitidas entre 21:29:01.281 e 21:29:01.370 UTC;
posteriormente Agents mostrou **4/5 disponíveis**, sem ajuste manual do pool.
Imagem: `build/runtime-lifecycle-m3c-live/pi-resumed-terminal.png`.

Isso acrescenta evidência real de recuperação, atendimento e reposição. Não
qualifica o desligamento desconhecido como crash induzido/controlado nem fecha
UI-A/M6. Last contact continua “never” na instalação M3c; a correção M3d está
validada apenas na instalação isolada. Codex não recebeu nova solicitação por
continuar pendente a restrição de quota do provedor já observada.
