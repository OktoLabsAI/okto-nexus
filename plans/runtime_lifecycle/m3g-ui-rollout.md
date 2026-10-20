# M4d2 + M3g — Implantação e verificação real

Em 17/10/2026 foram implantados os commits Nexus `132d8ba` e `8c5cf2b`, após
50 testes instalados de recuperação/manutenção e 18 testes instalados de pool.
As duas campanhas preservaram suas entradas. Core e Connector não mudaram.

## Encerramento e instalação

A geração 70 não tinha chamadas, sessões ou turnos ativos na verificação anterior
ao encerramento. O sinal normal foi enviado somente à console cuja identidade
foi conferida. O servidor registrou DRAINED às 03:50:00 UTC, concluiu o shutdown
e saiu; não houve finalização forçada. Os 265 bancos foram copiados depois da
saída do processo, em `build/runtime-m3g-live/before/`.

A wheel Nexus 0.3.1 instalada tem SHA-256
`5295d1ef4563d83c528605f628f94a05ef0788d47fcabf89a2a3b2555f81550d`.
Foram comparados os arquivos instalados com os artefatos e verificadas as
dependências: Nexus 541 arquivos, Core 0.0.12 com 156, Connector 0.0.10 com 98.

A geração 71 iniciou no servidor PID 40832, launcher 25092, na porta 8202.

| Agente | READY (UTC) |
| --- | --- |
| Codex | 03:51:54.284606 |
| Claude | 03:51:55.401287 |
| Pi | 03:52:01.411799 |

O Pi iniciou a recuperação individual às 03:51:53.331629: aproximadamente oito
segundos até READY. Isso não é uma comparação controlada com o primeiro backfill
da geração 70, que já havia produzido certificados. A independência de histórico
lentamente processado foi verificada nos testes instalados M4d2.

## Pool e chamada pelo Meta-harness

As quatro reservas antigas recusadas antes do Core foram recolhidas
automaticamente. Nenhum estado do banco foi editado manualmente. Foram criadas
quatro reservas novas às 03:56:39.697 UTC; a observação às 03:58:19 confirmou
as quatro WARM. A UI Agents mostrou os três agentes locais online e Pi com
4/5 disponíveis.

Pelo Meta-harness, foi enviada uma mensagem privada ao Pi, no workspace Techridy,
com assunto `M3g · Pi pool restaurado`, pedindo apenas `M3G_PI_OK`, sem ferramentas
ou alteração de arquivos. A interface mostrou a resposta esperada e 1/1 ACK.

O registro durável confirmou que a chamada usou uma das quatro sessões do
snapshot anterior ao envio. Da admissão até RUNNING foram 0,566 s; até SUCCEEDED,
9,944 s. A sessão consumida não foi reutilizada. Às 03:59:58, as três sessões
aquecidas restantes e uma nova reposição estavam WARM, sem backoff pendente.
Essas medidas são uma amostra funcional real, não um benchmark de carga.

Não houve nova chamada ao Codex por causa da quota externa registrada em L5.
Pi e Claude também responderam na geração 70 antes dessa implantação; essa
evidência anterior está separada em `m3f-diagnostic-contention.md`.

## Pendência de descoberta inicial

READY e inventário utilizável ainda têm ritmos diferentes: a primeira reserva
de aquecimento só foi criada cerca de 4m46s após o início da recuperação. Durante
esse intervalo, o worker de inventário foi observado calculando fingerprints.
O servidor respondia e os agentes estavam READY; o pool ainda não estava pronto.
Não se atribui todo o intervalo exclusivamente ao hashing sem medir também
descoberta, publicação e backoff. A disponibilidade efetiva por harness e o custo
da primeira descoberta continuam pendentes em M3/M7, agora registrados em L14.

Houve timeouts no controle da aba antiga do Chrome. A validação final foi feita
em uma nova aba do mesmo navegador, sem trocar de mecanismo de automação nem
substituir o envio pela UI por uma chamada direta à API.

Evidências privadas: `build/runtime-m3g-live/observations.jsonl`, backup, dumps,
`build/runtime-m3g-installed/` e `build/runtime-m4d2-installed/`. A instância foi
deixada em execução. A reestruturação completa permanece em andamento.
