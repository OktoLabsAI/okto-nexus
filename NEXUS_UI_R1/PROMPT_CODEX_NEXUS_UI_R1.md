# Prompt de execução — Nexus UI-R1

Copie o texto abaixo e disponibilize o plano e o ledger no ambiente do Codex.

```text
Implemente o plano PLANO_CODEX_NEXUS_UI_SIMPLIFICADA_HOME_ONBOARDING_R1.md,
com o ledger NEXUS_UI_EXECUTION_LEDGER_R1.json. Comece pela PR-00 e avance
por tarefas pequenas e testáveis. A inspeção foi feita na branch
feature/v0.3.4 do OktoLabsAI/okto-nexus, SHA
3d95aad8c1b5d2e6354cd872512586fd7a02aec9. O Connector de referência é
feature/v0.0.12, SHA a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b.
Esses SHAs são baseline de análise, não autorização para retroceder o checkout.

Antes de editar, leia AGENTS/CONTRIBUTING/CI atuais, registre branch/HEAD,
working tree, pins e drift. Há implementação de Home em andamento: preserve-a,
reaproveite os serviços, controllers, testes, alvos e controles já entregues.
Não faça reset/clean destrutivo, force-push, release, deploy ou campanhas pagas
sem autorização específica. Não altere a instalação pessoal do usuário.

REQUISITOS NÃO OPCIONAIS:
1. Quatro destinos principais: Home, Conversations, Graph e Artifacts.
   Advanced é entrada secundária, com grupos e acesso às páginas atuais.
2. Home tem uma única região principal de acompanhamento. Trabalho, harness,
   sessão, pergunta e resultado correlacionados ficam juntos. Não criar menu,
   tela ou lista paralela de Harnesses/Execuções/Sessões.
3. Abrir a linha mostra o contexto/sessão exatos num painel contextual,
   reutilizando o terminal de eventos somente leitura e controles canônicos.
   Incluir sessões sem operação e atividades iniciadas por outros agentes.
4. Perguntas/aprovações/erros/resultados ficam no básico e no sino global,
   inclusive com fallback da Home antiga. Advanced não é controle de acesso.
5. Onboarding obrigatório: retomar conexão existente OU adicionar outro
   harness ao mesmo projeto, sem o usuário precisar inventar --profile.
   Preservar scripts explícitos, IDs, checkpoints, revisões e permissões.
   Implementar no CLI local, no onboarding da UI e no Connector respeitando
   a autoridade de cada superfície. Não deixar isso como follow-up opcional.
6. Retomar conexão, continuar sessão, abrir nova sessão e recuperar envio
   pendente são intenções diferentes. Não usar a sessão mais recente por
   heurística; resultado incerto não autoriza nova execução.
7. Preservar daemon/serviço e ciclo pelo terminal; UI não vira obrigatória.
   Nova conexão não recria o serviço, renova grant ou altera outra conexão.

O layout multi-listas do plano HOME-R1 é substituído por esta composição única,
mas seus invariantes e evidências continuam. Não refaça Core/protocolos ou
Attention/setup/receipt. Não una primeiras páginas de várias fontes em React
para fingir inventário completo: correlação e paginação são escopadas no backend.
Mantenha identidade interna de views e URLs ao trocar rótulos públicos.

Siga PR-00..PR-08 e dependências do ledger. Ao terminar cada tarefa, execute
seus cenários e atualize evidências/limitações. IMPLEMENTED não é VERIFIED;
fixture não é harness real; teste Node não é navegador nem leitor de tela.
Preserve bloqueios de qualificação anteriores aplicáveis. Ao fim de cada etapa,
informe mudanças, testes, regressões, efeitos/migrações, rollback e próximo passo.
Não encerre a entrega apenas com o menu ou com a Home: o requisito obrigatório
de adicionar/retomar múltiplas conexões faz parte do gate final.
```
