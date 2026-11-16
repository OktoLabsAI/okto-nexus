# Leia primeiro — pacote Nexus UI-R1

Este pacote consolida a navegação simplificada, a Home com acompanhamento único e o onboarding obrigatório para retomar uma conexão ou adicionar outro harness ao mesmo projeto.

## Arquivos

- `PLANO_CODEX_NEXUS_UI_SIMPLIFICADA_HOME_ONBOARDING_R1.md`: especificação completa de produto e implementação, com 47 tarefas, 145 cenários, 18 requisitos e 9 entregas incrementais.
- `NEXUS_UI_EXECUTION_LEDGER_R1.json`: acompanhamento inicial, dependências e rastreabilidade entre requisitos, tarefas e testes. Todas as tarefas começam TODO; todos os testes começam NOT_RUN.
- `PROMPT_CODEX_NEXUS_UI_R1.md`: instrução de arranque para o Codex. O mesmo texto está na seção 19 do plano.
- `MANIFESTO.json`: tamanhos e hashes dos arquivos para conferência de integridade.

## Como usar

Coloque plano e ledger em local acessível ao Codex e envie o prompt de execução. O primeiro incremento é PR-00: ler instruções do repositório, registrar checkout/HEAD, reconciliar trabalho já implementado e preservar alterações em andamento. Não fazer checkout destrutivo para o SHA de referência.

Referência estática do Nexus: `feature/v0.3.4`, SHA `3d95aad8c1b5d2e6354cd872512586fd7a02aec9`. Connector de compatibilidade: `feature/v0.0.12`, SHA `a8bd48bdc6d6e835c55eb601a7e7fa316453aa7b`. Esses snapshots explicam o plano; não fixam a branch de trabalho do executor nem comprovam uma instalação em produção.

## Decisões obrigatórias

A navegação principal contém Home, Conversas, Grafo e Artefatos, com Avançado como entrada secundária. A Home possui um acompanhamento principal único, que abre a sessão exata no contexto. Perguntas, aprovações e entregas permanecem no básico. Retomar uma conexão e adicionar outro harness sem nome técnico de perfil são parte obrigatória da entrega, não trabalho opcional.

O layout de listas paralelas do plano HOME-R1 anterior é substituído por esta composição. Seus invariantes, contratos canônicos e evidências permanecem; não sobrescreva seus ledgers nem apague as fontes existentes.

## O que foi validado neste pacote

Foi conferida a consistência estrutural dos IDs, contagens, referências, dependências, cobertura de rastreabilidade e arquivos. Nenhuma suite, campanha de navegador, execução de Nexus/Connector ou inferência de provedor foi realizada para elaborar este pacote. Os cenários devem ser executados e registrados pelo Codex, com evidências e limites reais. O plano não autoriza deploy, release, alteração da instalação pessoal ou uso pago de provedor sem autorização específica.
