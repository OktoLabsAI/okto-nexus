# SI-041 · Qualificação e decisão de rollout

O plano continua em execução. O candidato mantém a interação de sessão como opt-in. A evidência controlada sustenta as combinações abaixo e o rollback testado. A liberação geral depende das etapas externas registradas neste relatório. [Matriz por instalação](si027-session-capability-matrix.md) [Auditoria estruturada](si041-qualification-checkpoint.json)

| Instalação revisada | Evidência controlada | Limite atual |
| --- | --- | --- |
| Codex app-server 0.157.0 e viewer 0.170.0 | A mesma thread sobreviveu à anexação, à escrita revisada e ao detach em Windows. Via Connector, a reorientação pelo visualizador atingiu o turno em execução e preservou uma entrada separada na fila. Os ensaios usaram um serviço Responses simulado. [Jornada e preset](si038-codex-effective-preset.md) [Reorientação pelo visualizador](si022-codex-remote-native-steer.md) | O teste de conexão com a conta e o modelo da campanha continua pendente. O modelo `gpt-5.3-codex` falhou na campanha anterior. [Preparação](si038-codex-campaign-preflight.md) |
| Pi 0.87.1 | O Edge e o editor nativo escreveram na mesma sessão pelo Connector. O ensaio confirmou a fila, a reorientação, o detach e a abertura separada com escopo exato. [Jornada](si036-pi-browser-writer-roundtrip.md) [Fila e steer](si025-pi-connector-shared-queue-steer.md) [Abertura separada](si030-pi-connector-separate-session.md) | A prova cobre Windows e Connector na mesma máquina, com respostas determinísticas. A campanha com provedor e o ensaio entre máquinas continuam pendentes. |
| Claude Code 2.1.328 | O terminal gerenciado em modo `plan` permitiu acompanhamento e decisões pelo navegador. No Windows, o compositor do CLI e a Home compartilharam a fila pelo Connector. Os atalhos de reorientação e interrupção foram exercitados pelo Connector e pelo executor local do Nexus. [Decisões no navegador](si036-claude-browser-roundtrip.md) · [Escrita pelo CLI](si026-claude-cli-writer.md) · [Controles no visualizador](si026-claude-viewer-controls.md) | Os ensaios ocorreram na mesma máquina com respostas simuladas em loopback. A campanha com provedor e a avaliação com participante ficam em aberto. A qualificação em outros hosts fica para outro corte. |

## Compatibilidade e rollback

O wheel atual migrou a cópia histórica do esquema 168 ao 190. Foram aplicadas 22 migrações. A reaplicação retornou zero. As colunas antigas de 90 linhas em 161 tabelas ficaram iguais, e o Core atual interpretou os quatro recibos canônicos com os hashes originais. As três respostas HTTP autenticadas permaneceram iguais na origem, na base atualizada e na restauração com Nexus 0.3.7. As consultas anônimas retornaram 401. O novo campo de pausa e o marcador de entrada literal assumiram `0` na migração. Os campos opcionais de lançamento e retomada ficaram nulos na sessão histórica. A base de origem e o backup preservaram seus hashes. [Visão estruturada do ensaio](si041-qualification-checkpoint.json)

Uma segunda cópia histórica, no esquema 188, continha dois registros de retomada e oito recibos. A atualização preservou seus dados e os `rowid` dos registros de retomada. As verificações de integridade e as 65 regressões de migração, fila e recibos passaram nos wheels instalados. [Auditoria estruturada](si041-qualification-checkpoint.json)

A pausa global impede novas admissões e deixa a fila aceita seguir. O Edge e um Pi real provaram isso durante um turno em execução. Para rollback de versão, conserve os recibos em andamento e use uma cópia do backup pré-migração com os wheels anteriores. [Pausa global](si041-native-admission-rollback.md) [Procedimento](../../docs/terminal-work.md#roll-back-the-session-interface)

## Pendências do ledger

O verificador comparou os 41 itens de trabalho, 148 cenários, 24 requisitos e oito fases com o plano preservado. O ledger registra 118 cenários em `PASS` e 30 em `NOT_RUN`. O resultado do verificador confirma a estrutura e os vínculos de evidência. As tarefas de regressão, auditoria, navegador, empacotamento, documentação e rollout que já possuem trabalho registrado passam de `TODO` a `IN_PROGRESS`. [Verificador](../../tools/check_session_interaction_ledger.py) [Ledger](../NEXUS_SESSOES_INTERATIVAS_LEDGER_R1.json)

Para repetir a checagem estrutural, execute `python tools/check_session_interaction_ledger.py` na raiz do Nexus.

- `SI-T-G01` a `SI-T-G20` e `SI-T-I01` a `SI-T-I09` incluem campanha no nível de aceite. A preparação da primeira rodada Codex precisa do candidato e da conta confirmados, de um modelo que passe pelo teste de conexão e de autorização específica para o orçamento. [Proposta e evidências anteriores](si038-codex-campaign-preflight.md)
- A validação do Connector desta etapa usa Nexus e Connector na mesma máquina. O ensaio nativo confirmou a recuperação de uma abertura após perda da resposta, com os dois processos encerrados pelo fluxo canônico. O ensaio entre máquinas fica adiado e `SI-T-H01` conserva `NOT_RUN`. [Ensaio local com Pi](si030-pi-connector-current-host.md)
- `SI-036` mantém aberto o aceite do participante. O ensaio com Orca e Chromium cobre os avisos de fim de turno na combinação registrada. A validação dos leitores de tela do Windows continua pendente. [Edge e Pi](si036-pi-browser-writer-roundtrip.md) [Orca](si017-orca-live-turn-announcements.md)
- A qualificação adicional no macOS fica adiada para outro corte. As evidências já coletadas continuam vinculadas a `SI-037`. O workflow de macOS passa a ser disparado manualmente, e a rodada do renderizador hospedado foi cancelada. [Prova existente no macOS](si037-macos-pi-probe.md) [Rodada cancelada](https://github.com/OktoLabsAI/okto-nexus/actions/runs/45391438377)

Este marco registra a atualização da base histórica e a decisão de manter o rollout pendente. O verificador e as evidências podem ser revertidos pelo commit. A reversão do ambiente testado já foi exercitada com uma cópia pré-migração.
