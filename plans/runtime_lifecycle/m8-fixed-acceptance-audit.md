# M8 — auditoria dos critérios fixos após o rollout

Data: 2026-10-20 UTC. Este quadro aplica somente os critérios de
[`plan.md`](plan.md) para M2/M3/M4/M8, a matriz mínima e os gates UI-A/B/C.
Não cria outro gate. O usuário escolheu o Connector local para qualificar o
caminho remoto nesta campanha; outro host físico permanece fora da afirmação.

| Critério fixo | Evidência atual | Estado |
| --- | --- | --- |
| Backup e migração reversíveis | [Backup global](m8-global-preupgrade-backup.md) validado novamente em 2026-10-20; [restore e migração isolados](m8-global-backup-migration-rehearsal.md) preservaram 7 agentes, 325 mensagens, 337 entregas, 6 handoffs e 3 artefatos, com FK 0. O home global migrou de schema 145 para 152 com as mesmas identidades e FK 0. Um [novo backup offline](m8-final-prewheel-backup.md) do home já migrado foi validado antes do wheel CI. | Comprovado. |
| Upgrade/downgrade incompatível | [M6k](m6k-upgrade-rollback.md) recusou o schema novo na wheel antiga sem alterar hashes e reabriu na atual. | Local comprovado. |
| Mesma carga anterior/atual | [M8 load](m8-same-load-comparison.md): as duas wheels passaram a mesma fixture de 100 mil identidades; a atual foi mais lenta nessa amostra. | Comparação registrada, sem alegação de ganho. |
| Dependências instaladas | Core 0.0.12 CI `39336889894` e Connector 0.0.10 CI `39343006146` passaram; o Nexus 0.3.1 usa Core 0.0.12. O [wheel CI do Nexus](m8-global-ci-wheel-rollout.md) foi instalado no home global com seu hash confirmado. | Comprovado. |
| Matriz Nexus instalada | O run [39472894540](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39472894540) concluiu 24/24 jobs instalados em Linux e Windows, Python 3.11–3.13, no commit `252788f`. Os problemas das fixtures [Pi](m8-ci-pi-bridge-timeout.md), [presença](m8-ci-presence-race.md), [Claude](m8-ci-claude-teardown.md) e [handoff](m8-ci-handoff-inventory-refresh.md) ficaram resolvidos nessa matriz. | Comprovado. |
| UI-A/B/C reais | [UI-A](ui-a-installed-restart-evidence.md), [UI-B](ui-b-evidence-audit.md) e [UI-C](m8-uic-installed-ui.md) registram os fluxos pelo navegador com Pi, Claude e Codex, incluindo recuperação e Connector local. O [rollout global](m8-global-ci-wheel-rollout.md) acrescentou um turno Pi pela UI com resposta exata e 1/1 ACK após instalar o wheel CI. | Comprovado no escopo local. |
| Rollout global e invariante final | O [wheel CI](m8-global-ci-wheel-rollout.md) roda no home global em schema 152 com dados preservados e FK 0. Pi, Claude e Codex aparecem Online; Pi respondeu pela UI, a sessão consumida foi aposentada e o pool ficou em 4/5. Um Server e quatro processos Pi nativos correspondem às quatro sessões aquecidas; não restou processo da sessão consumida. | Comprovado no cenário qualificado. |

A matriz mínima já tem evidências direcionadas para seus eixos: processo
nativo e fake, transporte embedded/Connector local, sessões persistentes e
one-shot, warm/cold e handoff ([UI-A](ui-a-installed-restart-evidence.md),
[UI-B](ui-b-evidence-audit.md)); crashes e fronteiras de intent/spawn/birth/
handshake/receipt/ACK ([M2h](m2h-late-crash-cuts.md)); fila, deadline e carga
([M7o](m7o-installed-load-results.md), [M8 load](m8-same-load-comparison.md));
quota de operação/artefato e falha de gravação
(`tests/execution_r4/test_admission_capacity.py`,
`test_canonical_artifact_boundaries.py`,
`test_canonical_artifact_maintenance.py`, `tests/test_runtime_event_journal.py`);
permissões/MCP e artefato grande ([UI-C](m8-uic-installed-ui.md)); criação
durante recovery e estado em Agents/Graph/terminal
([UI-B](ui-b-evidence-audit.md), [UI-C](m8-uic-installed-ui.md)). Esses
recortes não substituem a matriz Nexus completa, e o teste de Connector em
loopback não demonstra uma rede ou máquina remota física.

Os critérios fixos desta auditoria estão satisfeitos no escopo local autorizado.
O host Connector físico separado continua fora desta campanha, conforme a
decisão do usuário. A causa da parada anterior da instância global não foi
estabelecida; o checkpoint final comprova a recuperação após o novo start.
