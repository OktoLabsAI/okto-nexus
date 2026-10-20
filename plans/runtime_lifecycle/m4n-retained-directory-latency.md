# M4n — latência do histórico físico retido

Data: 2026-10-20 UTC. Medição da wheel Nexus 0.3.1 instalada em `build/m2g-nexus-verify`, com Core 0.0.12. `tools/benchmark_runtime_directory_audit.py` criou um Server descartável migrado, linhas históricas fechadas e arquivos físicos vazios em um diretório isolado; não usou harness real nem o Nexus global. A instrumentação contou passos VM SQLite em todas as amostras.

| Arquivos retidos | Montagem da fixture | `audit_files()` | Lotes | Maior lote | Passos SQLite |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1.000 | 5,632 s | 0,092 s | 8 | 128 | 15.263 |
| 10.000 | 15,115 s | 0,991 s | 79 | 128 | 152.606 |
| 100.000 | 153,921 s | 9,798 s | 782 | 128 | 1.525.805 |

A auditoria física permanece linear no número de arquivos, aproximadamente 0,10 ms e 15,3 passos SQLite por arquivo nesta máquina. É um custo conhecido de admissão para detectar arquivos não atribuíveis após downtime; não equivale ao custo da reconciliação de pendências, indexada nos checkpoints M4d4j–m. A amostra anterior M4d4f1 havia medido 27,520 s com 100 mil arquivos e os mesmos 1.525.805 passos, mas sob outra carga/fixture, logo não serve como afirmação de ganho de performance. O limite de lote 128 foi respeitado. Não foi introduzido cache que pudesse ocultar alteração física offline.

O benchmark encerrou, removeu sua fixture e devolveu a memória livre de 9,17 para 9,97 GiB. O aceite técnico local de latência com 1k/10k/100k fica registrado com o custo linear explícito. M4 ainda exige o rollout global controlado previsto; não será marcado completo antes disso.
