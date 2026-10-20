# M8 — auditoria dos critérios fixos antes do rollout

Data: 2026-10-20 UTC. Este quadro aplica somente os critérios de
[`plan.md`](plan.md) para M2/M3/M4/M8, a matriz mínima e os gates UI-A/B/C.
Não cria outro gate. O usuário escolheu o Connector local para qualificar o
caminho remoto nesta campanha; outro host físico permanece fora da afirmação.

| Critério fixo | Evidência atual | Estado |
| --- | --- | --- |
| Backup e migração reversíveis | [Backup global](m8-global-preupgrade-backup.md) validado novamente em 2026-10-20; [restore e migração isolados](m8-global-backup-migration-rehearsal.md) preservaram 7 agentes, 325 mensagens, 337 entregas, 6 handoffs e 3 artefatos, com FK 0. O home global migrou de schema 145 para 152 com as mesmas identidades e FK 0. | Backup e migração global comprovados. |
| Upgrade/downgrade incompatível | [M6k](m6k-upgrade-rollback.md) recusou o schema novo na wheel antiga sem alterar hashes e reabriu na atual. | Local comprovado. |
| Mesma carga anterior/atual | [M8 load](m8-same-load-comparison.md): as duas wheels passaram a mesma fixture de 100 mil identidades; a atual foi mais lenta nessa amostra. | Comparação registrada, sem alegação de ganho. |
| Dependências instaladas | Core 0.0.12 CI `39336889894` e Connector 0.0.10 CI `39343006146` passaram; Nexus 0.3.1 usa os artefatos fixados conforme [triagem](m8-ci-triage.md). | Core/Connector aprovados; Nexus pendente. |
| Matriz Nexus instalada | Os 24 jobs do run [39370966337](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39370966337) passaram antes da correção de capacidade `82c8324`. Os runs [39389028762](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39389028762) e [39421464096](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39421464096) expuseram as fixtures [Pi](m8-ci-pi-bridge-timeout.md), [presença](m8-ci-presence-race.md) e [Claude](m8-ci-claude-teardown.md), já corrigidas. O run [39451295539](https://github.com/OktoLabsAI/okto-nexus/actions/runs/39451295539) passou 22 jobs; um falhou por `ECONNRESET` no `npm ci` antes do build e outro por [inventário transitório em teste de handoff](m8-ci-handoff-inventory-refresh.md). | Nova matriz completa pendente após correção da fixture de handoff. |
| UI-A/B/C reais | [UI-A](ui-a-installed-restart-evidence.md), [UI-B](ui-b-evidence-audit.md) e [UI-C](m8-uic-installed-ui.md) registram os fluxos pelo navegador com Pi, Claude e Codex, incluindo recuperação e Connector local. [Rollout global](m8-global-rollout-capacity.md) entregou respostas exatas com 1/1 ACK para os três após a correção. | Gates reais qualificados no wheel local do commit; checagem após wheel CI pendente. |
| Rollout global e invariante final | Core e Connector fixados foram instalados; o Nexus global está rodando em schema 152 com os dados preservados. Pi voltou a 4/5 instâncias aquecidas; três mensagens novas foram lidas e respondidas. | Substituir pelo wheel CI, reiniciar, inspecionar processos/slots e fechar o ledger. |

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

Sequência restante, sem ampliação de escopo: classificar os 24 shards do run
substituto; instalar seu wheel na instância global; verificar a mesma
preservação e uma resposta real curta pela interface; inspecionar processos e
slots pendentes; fechar o ledger e publicar o commit da milestone.
