# HOME-025 — fonte, sinal e fallback

Eventos são sugestões para refazer consultas autorizadas. O controller não aplica payload SSE ao DTO, não lê texto de ferramentas e não usa transporte live como prova de atualidade.

| Fonte/bloco | Sinal tratado | Evidência da origem / limite | Cobertura sem evento |
|---|---|---|---|
| Handoff: work/results/attention/agents/feed | `handoff.*` | `application/handoff.py` chama `_emit` nas transições; a projeção decide o estado | Poll 15 s e TTL do bloco; lease/aging não precisam de evento |
| Mensagens: work/agents/feed | `message.*` | `application/messages.py` emite `message.created`; mensagem não implica trabalho por si só | Poll 15 s |
| Execução/resultados | `execution.*`, `runtime.*`, `native.*`, `approval.*`, quando entregues pelo shell | Eventos do journal e recibos não são presumidos equivalentes ao stream workspace; sem promessa de sinal por toda mudança | Poll 15 s + `next_refresh_at` |
| Attention/preferences | `attention-invalidated`, `attention-reset`, quando encaminhados | Stream dedicado existente verifica watermark/retenção e emite controles; Home não abre outro stream. O shell global atualmente fornece seus eventos Nexus; controle não encaminhado continua coberto pelo fallback | Poll 15 s + deadline do resumo; mutação canônica bem-sucedida chama refresh |
| Observação externa | `observation.activity`, `observation.completion` | `application/observations.py` emite somente mudança material/completion, com visibilidade própria; renovar relatório sem mudança não exige evento | Poll 15 s + validade da projeção, nunca usar estado externo como execução nativa |
| Agentes/sessões/autoridade | `agent.*`, `session.*`, `authorization.*`, `operator.*` | Alguns fatos dependem só de clock/heartbeat/grant; existência de evento universal não foi assumida | Poll 15 s; auth/logout limpa; 401/403 limpa todo cache |
| Reconexão/retenção | mudança de streamStatus, reset/gap explícito | Snapshot completo substitui páginas anteriores; cursor do Server é diagnóstico, não ACK/autoridade | foco/retomada resnapshot; fallback permanece |

Debounce 350 ms (limite de lote 500 ms) e intervalo mínimo 1 s entre inícios de leitura. Apenas um worker em voo, inclusive após abort até conclusão. Com documento oculto, eventos/reconnect não iniciam leitura imediata: fallback 60 s; ao voltar, snapshot fresco. Relógio monotônico agenda; timestamps do Server calculam o intervalo de validade.

O feed usa templates fechados de negócio. Eventos desconhecidos, tokens e heartbeats não viram narrativa. Falha, verificação e decisão mantêm rótulos distintos; não há sumarização LLM nem agrupamento que apague esses registros.
