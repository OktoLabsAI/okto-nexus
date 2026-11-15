# HOME-R1 — baseline reconciliado

## Checkout e dependências

| Item | Observação |
|---|---|
| Branch anterior | feature/v0.3.3, 7e0cec1ed896d21667e5e6d6ee4246ce06e2c5ef; limpa |
| Referência do plano | 4ba6fa40383a4157eb0fe5e1b9a943bf112a089b |
| Main recuperada | 8d77b50c00b417c86818d027aed7497fababac34 |
| Drift de main | Três commits de testes: agentColor, npm test e tabela README/ErrorCode; integrados sem descartar R3 |
| Branch de trabalho | feature/v0.3.4, baseline integrado 970fd3deef61c913c92462b14925cefad8d0644d |
| Versão alvo | Nexus/dashboard0.3.4; Core0.0.14 e Connector0.0.12 preservados |
| Ambiente existente | Windows, .venv Python e frontend/node_modules disponíveis; nenhuma instalação pessoal alterada |

Os arquivos HomeView, App, AttentionInspection, useSSE, operatorUnread,
meta_harness_sessions, observability e agent_runtime_administration não diferem
da referência inspecionada. Os contratos necessários existem; falta a composição
operacional e a interação contextual. Não há justificativa inicial para alterar
Core/Connector.

## Comportamento existente e lacunas

Home é a seleção inicial. Ela faz quatro leituras independentes a cada15s e
mostra atalhos/resumos. Graph mantém nós globais; contar nodes não mede atuação
no workspace. conversation_sessions é operator-only e consulta detalhes por
sessão. Nenhuma dessas fontes será ampliada silenciosamente.

Attention já tem ocorrências, autorização, revisões/CAS, visto/adiado, TTL e
inspeções reais. Seu controller só opera preferências de ocorrências na página
atual; Home só recebe summary. A integração compacta precisa consumir a mesma
preferência sem uma página oculta nem contrato paralelo.

O shell tem stream geral e stream específico de Attention. Home não adicionará
um terceiro ou um por cartão. Snapshot/reconnect, lacuna de retenção e mudanças
apenas temporais ainda precisam qualificação R1. O timer atual de400ms do Graph
pode ser adiado indefinidamente em burst; não é o controlador proposto da Home.

O composer atual está em MetaHarnessView. Novo pedido pode reutilizá-lo, mas
metaHarnessSend não recebe session_id e não serve para continuar uma sessão
específica. A continuação utilizará o contrato runtime canônico e seleção exata.
Troca de workspace/view hoje pode desmontar inspeção fora do guard do modal;
esse caminho será protegido antes de desmontar.

## Validação e medidas

O frontend usa testes Node de lógica/SSR; eles não comprovam DOM, foco ou mobile.
Python dispõe de SQLite descartável, relógio controlado, TestClient e servidor
em processo real. Fixtures R1 serão compartilhadas entre classificação, SQL,
HTTP e navegador; integração com harness real ficará identificada separadamente.

As metas do plano (500ms p95,2s,200KiB e datasets1/10/100 agentes,
1000atividades/100000eventos) ainda não foram medidas neste plano. Resultados R3
não são benchmarks HOME-R1. Registrar fixture, hardware, relógio, amostras,
payload, queries e efeitos antes de afirmar cumprimento.

## Reversibilidade

Preservar a Home atual como fallback de apresentação. A flag nova não controla
Attention, observação, daemon, runtime ou grants. A primeira projeção é calculada
sobre fatos existentes, sem tabela de tarefas/filas Home. Índices só serão
adicionados com EXPLAIN e custo medido, usando a revisão real seguinte.
