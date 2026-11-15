# HOME-R1 — baseline e medições

## PR-00: consultas existentes, não a Home futura

[Qualificação reproduzível](evidence/pr00-fixtures/qualification.json) e
[dados](evidence/pr00-fixtures/baseline.json). Python3.13.1, Windows11,
SQLite migrado descartável, dependências existentes e fonte editável. Metadado
instalado era0.3.3 nessa execução; não é qualificação do wheel0.3.4.

Uma leitura warmup descartada,20amostras warm, perf_counter e p95 nearest-rank;
mesma transação, sem incluir sua abertura. SQL e total_changes observados.

| Operação | Dataset | p95 | SQL/leitura | JSON |
|---|---|---:|---:|---:|
| Graph atual | 6agentes/6handoffs | 1,142ms | 10 | 3.357bytes |
| Página de10eventos | 100agentes/1000handoffs/100001eventos | 0,122ms | 1 | 2.428bytes |

Encoding JSON não é renderização. Não há HTTP, autenticação, rede, browser,
coldstart ou provedor nessa medida. Não inferir Graph100agentes ou Home500ms.

## Qualificação necessária em HOME-031/032

Registrar hardware, dataset, cold/warm, amostras, p50/p95, queries, payload e taxa
de requests. Comparar1/10/100agentes,1000atividades e100000eventos; medir
EXPLAIN e custo de escrita antes de acrescentar índice. Metas iniciais do plano:
overview p95≤500ms, visão inicial≤2s e preview≤200KiB. Na baseline inicial: NOT_RUN.
Nenhum SLO de produção ou telemetria externa foi autorizado/alegado.

## HOME-031 — medição anterior à distinção de workers

Medição reproduzível por `scripts/measure_home_evolution.py`; fontes pinadas,
EXPLAIN e medidas completas em `evidence/pr05-performance/measurement.json`.
Windows11 10.0.26300, Intel64 Family6 Model141,16 CPUs lógicas,
Python3.13.1/SQLite3.45.3. Dados descartáveis e sintéticos; nenhum provedor.
Uma leitura inicial descartada,20 amostras warm e p95 nearest-rank. A leitura
inclui abertura do UoW; encoding JSON medido separadamente. Authorizer bloqueia
writes e cada leitura abre exatamente uma transação. Sem migration/índice novo.

| Identidades incluindo operador | Handoffs abertos | Eventos | p50 serviço | p95 serviço | SQL/GET | Payload máximo |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 10 | 100 | 526,36ms | 598,53ms | 46 | 9.629B |
| 10 | 10 | 100 | 404,18ms | 503,90ms | 46 | 10.794B |
| 100 | 10 | 100 | 400,77ms | 483,62ms | 46 | 10.794B |
| 100 | 1.000 | 100.000 | 805,30ms | 927,80ms | 46 | 11.154B |

A escala ampliada percorreu11 páginas e1.000 IDs distintos, sem serializar o
journal. O número de consultas ficou constante; há zero sessão/operação nativa
nesses dados. Não é benchmark de100 agentes executando. A meta inicial de500ms
**não foi atingida** em três dos quatro datasets. O payload ficou abaixo de200KiB.
Build/instalação e outros testes ocorreram na mesma máquina; não há isolamento de
CPU ou controle de cache do sistema operacional. Não declarar SLO de produção.

O perfil antes da consolidação encontrou projeção/políticas Attention repetidas.
Reutilizar políticas e materialização de statement reduziu consultas de130 para46;
`before-consolidation.json` e `after-consolidation-in-progress.json` preservam as
rodadas anteriores. Tempos entre rodadas têm ruído/concorrrência e não constituem
um ensaio A/B controlado. EXPLAIN foi registrado antes de qualquer índice;
nenhum índice foi adicionado sem demonstrar necessidade.

## Browser e taxa de leitura

No bundle estático servido por HTTP loopback, uma amostra com cache HTTP
desabilitado apresentou trabalho útil em1.124ms; o overview respondeu em1.092ms.
Assets transferidos: JS1.398.648B e CSS110.014B, incluindo overhead observado do
browser. Uma amostra não constitui p95 de render. Evidência em
`evidence/pr06-browser/initial-render.json`; o limite2s foi observado só nessa
amostra, não certificado como garantia.

Em15.569ms de observação foreground sem eventos injetados, essa página iniciou
dois GETs overview, espaçados15.007ms (0,1285requests/s). Fonte em
`evidence/pr06-browser/request-rate.json`. O teto sob burst de eventos é
qualificado separadamente pelo controller com relógio determinístico, não por
essa amostra de tráfego ocioso. Outros leitores do shell não entram nessa taxa.

## Medição final com1/10/100 workers no workspace

`measurement-final-workers.json` fixa o fonte `f948c5d7` e a revisão do utilitário.
O operador humano é contabilizado separadamente:1worker significa duas
identidades no banco. Cada worker tem uma sessão explícita de presença no
workspace, sem alegar execução nativa. O overview confirmou o total de workers
de cada caso. Ambiente anterior, com34.073.251.840B de RAM física medida por CIM;
o builder de pacote e os browsers podiam estar ativos na mesma máquina.

| Workers | Sessões de presença | Handoffs | Eventos | p50 serviço | p95 serviço | SQL/GET | Payload máximo |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 10 | 100 | 539,63ms | 583,46ms | 46 | 9.701B |
| 10 | 10 | 10 | 100 | 546,60ms | 649,06ms | 46 | 10.812B |
| 100 | 100 | 10 | 100 | 541,01ms | 573,78ms | 46 | 10.813B |
| 100 | 100 | 1.000 | 100.000 | 1.215,82ms | 1.361,12ms | 46 | 11.172B |

Todos os quatro casos excederam500ms p95. A revisão registra a meta como não
atingida e não faz afirmação de SLO. Queries permaneceram constantes, uma
transação porGET e zero writes. O caso ampliado preservou11 páginas/1.000 IDs.
A presença de100workers e as mudanças de projeção distinguem esse dataset dos
antecedentes; a comparação de tempos entre eles não é um A/B controlado.
Performance continuará como limite explícito na decisão de rollout. Nenhum
índice ou cache persistente foi introduzido para esconder o custo observado.
