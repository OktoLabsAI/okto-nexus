# Ledger da implementação R3

Plano fixo: [PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md](PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md).
Detalhamento por tarefa, cenário, dependência e evidência: [ledger.json](plans/agent_ops/ledger.json).
Relatório: [implementation-report.md](plans/agent_ops/implementation-report.md).

## 2026-11-05 — Preparação autorizada

- Recuperada `origin/main` dos três repositórios, sem reset nem perda de mudanças locais. O plano fornecido permaneceu intacto.
- Nexus: base `c1e78e26fb2bd57ace3370417a2cb7529856b603`; branch `feature/v0.3.3`; versão `0.3.2 → 0.3.3`.
- Core: base `19c99f15b17ae994653ad9e190964229a0e296e8`; branch `feature/v0.0.14`; versão `0.0.13 → 0.0.14`.
- Connector: base `a3017d97b6a295cb2b46b9dd391b4c04ed121ee2`; branch `feature/v0.0.12`; versão `0.0.11 → 0.0.12`.
- Ambos os consumidores passam a fixar Core `0.0.14`. Metadados do frontend alinhados com Nexus.
- Criado ledger detalhado com todos os IDs originais. Nenhum marco funcional está concluído.
- Core e Connector empacotados; payloads Python comparados byte a byte com o código atual. Mesmo wheel Core nos dois consumidores.
- Validação: Nexus 10 testes; Core 3; Connector 19; instalação isolada Connector/Core 2. Todos passaram. Evidências XML em `plans/agent_ops/evidence/preparation-*.xml`.
- BASE-05 verificado: validação de cobertura preserva 59 tarefas, 132 cenários, 28 invariantes e 17 critérios de conclusão. Isso comprova rastreabilidade, não implementação dos requisitos.
- Preparação enviada: Nexus `ff6ee26`, Core `2093863`, Connector `7fd37c8`.

## 2026-11-05 — PR-00: baseline, contratos e correções iniciais

- Mapeados os caminhos canônicos de setup/Finish, pergunta/decisão, mensagens, inbox, handoffs/claims e arquivos MCP nos três repositórios.
- Criados [baseline.md](plans/agent_ops/baseline.md), [adr.md](plans/agent_ops/adr.md) e [evidência da validação](plans/agent_ops/evidence/pr00-validation.md).
- Corrigida a constante de compatibilidade do inventário para Core `0.0.14`, identificada no teste mais amplo após o bump; adicionada proteção contra divergência do pin.
- Corrigida orientação de autenticação do onboarding e preservado o scheme/origin do endereço. Documentação distingue configuração gerenciada de participante adicional; instruções legadas de stdio/CI/auth foram atualizadas.
- Runner frontend existente exposto por `npm test` e incluído na CI. Build do dashboard atualizado.
- **216 testes de baseline passaram**, além dos 34 da preparação. Startup descartável medido: HTTP disponível em 7,811s; shutdown canônico chegou a `DRAINED`. Sem inferência real.
- BASE-01…05 verificados no escopo de inventário/documentação/rastreabilidade. BASE-06 tem mapa e medição de processo implementados; tempo até sessão/resultado real permanece não executado. PR-00 entrega o mapa para PR-01, sem declarar aceite funcional de M1.
- Commit/push do baseline: Nexus `3df2e95`.

## 2026-11-05 — PR-01, primeira fatia: exclusão do Server

- Server adquire locks do SO para home e banco canônicos **antes** de bootstrap/migrações. Homes distintos que usam o mesmo banco também ficam protegidos.
- Heartbeat antigo não transfere ownership. Metadata possui geração; PID legado incerto/reutilizado não autoriza takeover nem recebe sinal.
- Testes incluem dois processos reais concorrentes, saída abrupta do dono, recuperação e preservação do shutdown canônico. Evidências: [pr01-locks.md](plans/agent_ops/evidence/pr01-locks.md).
- SVC-02 segue em progresso no contrato completo de instância; a camada de exclusão do Server está implementada/testada. Fachada, start/reuse, prontidão, supervisor e integração Connector continuam pendentes conforme o plano.
- Corrigida a normalização de newlines da entrada HTML e regenerado o artefato pelo build, após o check de whitespace detectar CRLF duplicado.

- Commit/push da exclusão: Nexus `825ab2f`.

## 2026-11-05 — PR-01, segunda fatia: prontidão e status passivo

- Identidade inclui componente, home/banco canônicos e usuário efetivo do SO. HTTP local de operador informa geração, versão ativa, armazenamento e admissão.
- `okto-nexus service status --json` correlaciona esses fatos com os locks, sem criar estado nem iniciar processos. Divergência de versão, identidade e transporte permanece explícita.
- **36 testes passaram**. Um Server real em home descartável confirmou a mesma geração pelo CLI/HTTP e chegou a `DRAINED`; depois, status retornou `stopped`. [Evidência e limites](plans/agent_ops/evidence/pr01-readiness.md).
- SVC-01/02/04 continuam em progresso no contrato completo; start/reuse, supervisor e Connector permanecem pendentes.

- Commit/push da prontidão: Nexus `b3168f18`.

## 2026-11-05 — PR-01, terceira fatia: start/reuse e controle local

- Fachada de aplicação para inspect/start/ensure_running/stop/restart, com contexto resolvido persistido e recibo de inicialização protegido por locks do SO.
- Server destacado usa o mesmo `serve`; requisições concorrentes reutilizam a inicialização. Timeout não mata nem relança. Stop/restart usam o shutdown canônico e exigem a geração observada.
- Teste real com três CLIs concorrentes confirmou um único PID/geração, continuidade após saída dos CLIs, reutilização, restart, recusa de stop obsoleto e parada `DRAINED`.
- A integração com supervisor instalado, logs, recuperação de lançamento interrompido e Connector continua pendente. Saída do processo CLI não foi confundida com campanha de logout/reboot ou fechamento de terminal real.
- Evidência: [pr01-start-stop.md](plans/agent_ops/evidence/pr01-start-stop.md).

- Commit/push de start/reuse e controle local: Nexus `333e1381`.

## 2026-11-05 — PR-02, primeira fatia: prontidão e parada do Connector

- Locks recusados fecham seus descritores. Status exige lock do SO, nascimento do processo e resposta IPC correlacionada à instância/geração/versão; IPC indisponível deixa de parecer ausência do daemon.
- `daemon status` em diretório ausente não cria estado. O entrypoint foreground respeita `--state-dir`; stop do lifecycle inclui a geração e verifica recibo durável do drain.
- A regressão identificou cancelamento duplo durante fechamento HTTP de uma tarefa de attachment. Corrigido para aguardar a limpeza, sem repetir cancelamento.
- **46 testes específicos e 75 de regressão passaram**. O wheel candidato do Connector foi reconstruído e seus 104 arquivos Python conferidos contra o fonte; manifest do Nexus atualizado.
- Evidências, qualificação do pacote e limites: [pr02-connector-readiness.md](plans/agent_ops/evidence/pr02-connector-readiness.md).
- SVC-11 permanece em progresso: supervisor por instância, contexto persistido, serialização completa de lançamento e campanha remota real continuam pendentes.
- Pacote isolado: **2 testes passaram**, incluindo start/reuse/stop do wheel instalado fora do checkout. Connector enviado em `97c5e13`, com limpeza de código legado inalcançável em `c4ad79d`.

- Commit/push da coordenação Nexus: `eb808757`.

## 2026-11-05 — PR-02, segunda fatia: definição compartilhada de serviço

- Core recebeu contrato puro para definição de tarefa de login Windows por instância e fingerprint da definição exportada pelo SO; sem efeitos de instalação no import.
- **13 testes passaram**, incluindo validação nativa do XML pelo Task Scheduler com `TASK_VALIDATE_ONLY` e ausência da tarefa verificada antes/depois.
- Corrigido conflito real de declaração UTF-8 via COM Unicode. Wheel Core atualizado nos dois consumidores; 130 arquivos Python comparados ao fonte, lock e manifest coordenados.
- Essa fatia verifica o contrato e a sintaxe. Registro efetivo, CAS, controles do supervisor e campanhas de login continuam pendentes. [Evidência](plans/agent_ops/evidence/pr02-core-service-definition.md).

## Próxima dependência

Concluir as lacunas de PR-01 junto ao supervisor e ao Connector em PR-02 / SVC-05…12. A pendência de campanha de BASE-06 continua explícita; os critérios de trabalho real local/remoto e decisão pelo terminal de M1 permanecem intactos.

## Aceites externos ainda não executados

Campanhas reais de provedor, login/logout/reboot, serviço do usuário e Herdr permanecem pendentes. O plano exige autorização específica para credenciais reais, inferência paga e mudanças na instalação pessoal. Preparar primeiro os percursos e artefatos revisáveis; solicitar apenas a autorização ou o ambiente necessário ao chegar a cada campanha.
