# HOME-R1 — baseline e medições

## Estado consolidado — fonte `3d95aad8`

As medições finais abaixo usam os quatro volumes do plano: 1/10/100 workers
e o caso de 100 workers com 1.000 handoffs e 100.000 eventos. Cada experimento
tem 20 amostras warm por caso, após um warmup descartado; p95 é nearest-rank
(19ª das 20 amostras ordenadas). O operador humano fica fora da contagem de
workers. Os dados são descartáveis e sintéticos, com sessões de presença e
zero operações nativas.

Ambiente registrado: Windows 11 10.0.26300, 16 CPUs lógicas,
34.073.251.840 bytes de RAM, Python 3.13.1 e SQLite 3.45.3. Houve coordenação
para evitar build/pip/browser concorrentes durante as rodadas; a carga geral
do Windows e o cache do sistema operacional não foram controlados.

### Serviço e SQLite

[Medição completa](evidence/pr08-performance-final/measurement.json) e
[qualificação](evidence/pr08-performance-final/qualification.json). O tempo
abrange `HomeOverviewService.read`, incluindo abertura do UoW; encoding JSON
foi medido separadamente. O primeiro read com EXPLAIN foi descartado dos
tempos warm.

| Workers | Handoffs | Eventos | p50 serviço | p95 serviço |
|---:|---:|---:|---:|---:|
| 1 | 10 | 100 | 338,82 ms | 421,12 ms |
| 10 | 10 | 100 | 312,40 ms | 325,23 ms |
| 100 | 10 | 100 | 306,53 ms | 327,14 ms |
| 100 | 1.000 | 100.000 | 593,68 ms | **673,91 ms** |

O caso ampliado excedeu a meta de 500 ms nessa medição de serviço; os outros
três ficaram abaixo dela. Todos mantiveram 46 instruções SQL por leitura,
uma UoW e zero writes, com payload máximo de 11.458 bytes. A paginação do
caso ampliado percorreu 11 páginas e 1.000 IDs distintos.

Foram preservados 45 planos EXPLAIN por caso. Um
[profile adicional de uma leitura de serviço](evidence/pr08-performance-final/profile-one-get.json)
registrou domínio do custo de SQLite/overview, com 1.000 chamadas de projeção
de atividade e 1.000 de elegibilidade. Os planos incluem pontos correlacionados
de Attention; esses dados não demonstram dominância quadrática. Esse profile
process-first, sob cProfile, é separado das 20 amostras warm. Não houve
otimização baseada apenas nessa hipótese.

### Endpoint HTTP overview

[Medição HTTP completa](evidence/pr12-http-performance/measurement.json) e
[qualificação](evidence/pr12-http-performance/qualification.json). A rodada
dedicada usou TCP loopback real e quatro processos Uvicorn próprios, com
lifespan/discovery desabilitados na fixture e sem browser/SSE. Autorização
canônica de operador local, relógio, handler e campos da resposta permaneceram
inalterados. O timer cobre `httpx.Client.get` até receber o corpo completo;
parsing JSON e coleta de estatísticas pelo canal de controle ficam fora dele.

| Workers | Handoffs | Eventos | p50 HTTP | p95 HTTP |
|---:|---:|---:|---:|---:|
| 1 | 10 | 100 | 244,48 ms | 281,28 ms |
| 10 | 10 | 100 | 217,50 ms | 227,64 ms |
| 100 | 10 | 100 | 180,60 ms | 289,28 ms |
| 100 | 1.000 | 100.000 | 401,47 ms | **450,32 ms** |

Os quatro p95 do endpoint ficaram abaixo de 500 ms nessa amostra local.
As 84 requisições reais (80 warm e quatro warmups) retornaram 200/no-store
e os totais, escopo e cursor esperados. A observação do factory compartilhado,
incluindo usos de autenticação, confirmou uma UoW de leitura, 46 instruções
SQL, zero alterações de linhas e zero tentativas de mutação negadas por
requisição. O corpo máximo foi 11.477 bytes, sem compressão. Os quatro
servidores encerraram normalmente com código 0, antes da remoção dos dados
temporários. As fontes permaneceram iguais ao corte congelado; os 699 arquivos
Nexus também foram comparados ao wheel qualificado.

Serviço e HTTP são experimentos separados, realizados em momentos e processos
distintos, com diferenças de preparação, cache e instrumentação. Seus tempos
não formam pares para calcular overhead ou atribuir causalidade. A medição de
serviço com p95 de 673,91 ms permanece preservada. Os resultados HTTP atendem
à meta local do endpoint nos volumes medidos; não constituem SLO de produção,
garantia de cold start, p95 de renderização ou prova de carga com harnesses
nativos ativos. As seções seguintes preservam as rodadas históricas.

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

## Corte anterior `f948c5d7` com1/10/100 workers no workspace

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
