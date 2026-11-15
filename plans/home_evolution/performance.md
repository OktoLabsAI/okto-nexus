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
overview p95≤500ms, visão inicial≤2s e preview≤200KiB. Estado atual: NOT_RUN.
Nenhum SLO de produção ou telemetria externa foi autorizado/alegado.
