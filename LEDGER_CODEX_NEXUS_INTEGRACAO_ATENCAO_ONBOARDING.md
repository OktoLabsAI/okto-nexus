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
- Preparação pronta para commit/push nas três branches. Referências publicadas ficam no histórico do Git e no relatório.

## Próxima dependência

Concluir BASE-01…06 / PR-00, reutilizando daemon e serviços já presentes no Connector, setup/Finish e contratos canônicos de execução. Depois PR-01…03 para M1, mantendo os critérios de trabalho real local/remoto e decisão pelo terminal.

## Aceites externos ainda não executados

Campanhas reais de provedor, login/logout/reboot, serviço do usuário e Herdr permanecem pendentes. O plano exige autorização específica para credenciais reais, inferência paga e mudanças na instalação pessoal. Preparar primeiro os percursos e artefatos revisáveis; solicitar apenas a autorização ou o ambiente necessário ao chegar a cada campanha.
