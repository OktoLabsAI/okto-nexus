# RG-03 — revisão e candidato isolado

Base: `af056bb10d1c1a8602bbeb64a4be352918834a84`. Nenhum arquivo do checkout ou ledger foi editado. Requisito literal em `PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md:970`: “Observação idle não muda prioridade, fairness, elegibilidade ou reservas de claims.” O ledger consultado mantém RG-03 como `NOT_RUN`, sem evidência; este candidato não promove o status automaticamente.

## Prova existente consultada

| Asserção real | Fonte | Limite para RG-03 |
| --- | --- | --- |
| Publicar blocked/idle não muda snapshot das tabelas não OBS, exceto eventos previstos | `tests/test_observation_service.py:77` | Não prepara competição ou reserva ativa. |
| Idle/completion + seen não concluem turno SUBMITTED nem liberam o seguinte; só evento nativo canônico libera | `tests/execution_r4/test_external_observation_isolation.py:74` | Trabalho enfileirado de um agente; não verifica seleção por prioridade, fairness entre agentes ou reserva de claim. |
| Blocked/idle/working preservam fatos canônicos correlacionados e tabelas canônicas | `tests/test_observation_correlation_reads.py:138` | Projeção/leitura; não mede seleção/reserva do scheduler. |

Os quatro casos correspondentes (incluindo os dois parâmetros de isolamento) constam como PASS em `plans/agent_ops/evidence/pr10-correlation/candidate-v2/installed.xml`. O inventário exato de testcases/XML consultados está em `retained-evidence-map.json`; inclui a rodada inicial com falhas e a correção posterior de PR10, sem apagá-las. Não se somam campanhas repetidas como testes únicos.

Comportamentos canônicos reaproveitados, sem idle nas provas originais:

- `test_canonical_priority.py:13`: prioridade de endpoint e afinidade original.
- `test_handoff_pool_priority.py:19`: FIFO one-shot anterior ao handoff automático.
- `test_canonical_dispatch_fairness.py:11`: três reservas de abertura de um agente deixam um crédito para outro.
- `test_handoff_runtime_candidates.py:104` e `:310`: opt-in e audiência/dependências canônicas antes de preparar candidatos.
- `test_handoff_runtime_attempts.py:62`: recuperação da mesma reserva após resposta perdida.

Não foram localizados testcases desses nomes nos XMLs retidos em `plans/agent_ops/evidence`; isso não afirma que nunca tenham sido executados em outras campanhas.

## Delta finito

Um único arquivo novo: `tests/execution_r4/test_external_idle_scheduler_isolation.py` (seis casos).

1. Prioridade: duas bindings reais; working → idle mantém seleção do endpoint de maior prioridade, afinidade e uma única execução nativa.
2. FIFO: scheduler real antes/depois de idle permanece `EARLIER_WORK_PENDING`; dois consumidores anteriores, claim epoch e uso do grant permanecem iguais.
3. Fairness: três aberturas sintéticas suspensas continuam ocupando seu quinhão; idle não libera a quarta do mesmo agente nem impede a abertura do outro.
4. Elegibilidade, opt-in: idle não habilita auto-claim; a mudança explícita da política continua necessária.
5. Elegibilidade, audiência: idle não permite ao candidato alcançar um criador fora de sua audiência; somente retirar a restrição canônica da fixture permite descoberta.
6. Reserva: uma reserva Core real em `RESERVED` permanece com os mesmos IDs, escopo, revisão de capacidade, estado, consumo e tabelas canônicas; replay não renova o TTL nem cria/consome claim.

As fixtures existentes criam HTTP TestClient, SQLite migrado, Core instalado e peer nativo explicitamente sintético. Credenciais são somente as geradas pela própria fixture isolada. Não há daemon de usuário, provedor, cofre pessoal, browser, processo pessoal ou prova de M1/M2. A disponibilidade sintética é declarada; nenhuma coluna de prontidão é forjada para fazer o teste passar.

## Validação

`source-wheel-proof.json` comprova os 690 arquivos de pacote iguais entre checkout atual e wheel Nexus `9b18dc0c69673bb730198ca461f2464c8ee4ae3fdc1226f22ffcb8140783412f`.

Execução usa o venv isolado pré-existente `nexus-ci-connector-refresh-la1tb1l6/venv`, com Core `5721e462add21d65380f070a68db07a653a498a78d4be9ea0cf949909d3cfecb`, Connector `a8cf18105fa1cdca0443b6a3be08972d5576f72f3ce07e5a19dd9fc7cd59ae5a` e MCP 1.30.0. Testes são cópia Git da base, `python -I -m pytest`, sem pythonpath para código de checkout; cache pytest, XML, logs e bancos de fixture ficam neste Temp. As primeiras rodadas puderam escrever bytecode apenas no snapshot ou nesse venv próprio; a rodada qualificada usa também `-B`. O runner anterior já comprovou `pip check` sem dependências quebradas. O manifesto final registra o intérprete e os módulos carregados.

`rg03-initial.xml/log/json` e `candidate-initial.py` preservam a primeira rodada: quatro PASS, uma falha de asserção do próprio candidato, que exigia TTL remanescente idêntico (`60000` versus `59926`). O contrato Core define esse campo como observação decrescente. O candidato final exige redução monotônica e igualdade dos demais campos; não houve correção de produto.

`rg03-final.xml/log/json` contém seis PASS. Após revisão do root, somente imports de fixtures foram explicitados para Ruff, sem mudar asserções. `ruff-initial.log/json` retém F811 com a forma `x as x` nos nomes também recebidos como argumentos; alias `*_fixture` + reexport explícito corrigem esses casos. `ruff-final.log/json` passa sem ignores. `rg03-qualified.xml/log/json` reexecuta os seis casos no arquivo exato final. Não se somam as rodadas como testes diferentes.

`report.json` e `manifest.json` consolidam contagem, escopo e hashes; `public/` contém apenas a allowlist curada, sem bancos, homes, tokens ou arquivos privados. Não há benchmark de latência; a qualificação RG-05 do root pôde executar em paralelo.

`candidate.patch` possui caminhos relativos ao repo, foi preparado fora do checkout e deve passar revisão do root antes de aplicação. Não há commit/push desta tarefa.
