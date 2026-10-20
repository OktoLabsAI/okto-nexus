# M8 — comparação instalada sob a mesma carga

Em 2026-10-20, no mesmo Alienware m15 (Windows 11, 16 CPUs lógicas,
Python 3.13.1), executei sequencialmente `test_ns14_04[load]` contra wheels
instaladas do Nexus 0.3.0/Core 0.0.11 (snapshot `a63b232f`) e do Nexus
0.3.1/Core 0.0.12. A fixture, copiada para o snapshot antigo, foi idêntica:
100.000 identidades, 200 lotes de 500 leituras, um SQLite real, HTTP/WSS,
dois executores simulados, filas saturadas e 20 submissões rejeitadas. Não
houve processo nativo de Pi, Claude ou Codex; o binário simulado só alimentou
o inventário. Os ensaios rodaram um de cada vez, sem Nexus global.

| Medida | Baseline 0.3.0 | Atual 0.3.1 |
| --- | ---: | ---: |
| Resultado | passou | passou |
| Tempo total do teste | 171,62 s | 219,98 s |
| Fase das 100.000 identidades | 73,78 s | 92,10 s |
| Tempo somado dentro dos 200 lotes | 65,06 s | 79,99 s |
| Maior lote | 0,416 s | 0,886 s |
| Latência do comando de controle | 0,907 s | 2,091 s |
| Latência do segundo executor | 0,294 s | 0,462 s |
| Entradas no cache ao final | 4.096 | 4.096 |
| Rejeições durante fila cheia | 20 | 20 |

Os JUnit XML completos estão nos artefatos locais ignorados
`build/m8-baseline-ns14-peer.xml` e `build/m8-current-ns14-peer.xml`. É uma
amostra por versão; tempos de host e de agendamento variam. O ensaio mostra
que a versão atual completou as mesmas operações, mas foi mais lenta nesta
medição. Não há evidência de ganho de desempenho nem limite de latência de
M8 definido para essa comparação.

Antes da comparação válida, a fixture antiga perdeu seu executor simulado na
fase HTTP porque só enviava heartbeats durante a fase de identidades. O
processo real do Connector mantém esse sinal independentemente das chamadas.
Um heartbeat independente foi acrescentado apenas à fixture, sem alterar
produto, carga, limites de fila ou critérios. A tentativa exploratória de
chamar a manutenção completa a cada requisição foi revertida. Ambas as
versões passaram com a mesma correção da fixture. A matriz instalada completa
e o rollout global controlado permanecem gates separados.
