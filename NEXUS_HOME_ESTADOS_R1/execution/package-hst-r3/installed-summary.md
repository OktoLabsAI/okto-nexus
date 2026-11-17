# Regressão instalada R3 — corte final

**746 PASS, 8 SKIP, 0 FAIL, 0 ERROR, 0 NOT_RUN** entre 754 nodes coletados em dois shards sem fail-fast. Shard 0: 469 PASS, stdout pytest 710,59 s. Shard 1: 277 PASS e 8 SKIP, stdout pytest 564,94 s. Rodaram em paralelo com jornadas funcionais do browser; os tempos não são benchmark.

O pacote efetivamente importado foi o R3 `5e280e9c55f579811a326ce26fe71423d67e14237d39f978341b2c3e221b5c44`, candidato `042585b4c622948261a50b550fec3616e2743e45`, no prefixo próprio `nexus-hst-r1-package-2f5l3545/venv`. Cada shard executou `-I -B` fora do checkout, com stdin PIPE fechado, homes próprios e helpers copiados sem `src`. Origem de todos os módulos Nexus/Core/Connector carregados foi verificada no início e no fim. As cópias dos testes não tiveram asserts ou argv reescritos.

Nos snapshots capturados antes/depois: 1.821 pins de fonte/testes, 1.031 arquivos de payload e helpers foram idênticos. O helper externo foi comparado ao Git blob do candidato e à fonte, além da cópia. Testes copiados também permaneceram idênticos aos hashes de fonte. Nenhum timeout, sinal, force ou processo próprio conhecido remanescente. O polling de processos não é apresentado como inventário de todos os filhos curtos.

Os oito SKIPs são literais: três exigem semântica POSIX de filesystem e cinco exigem stdin de terminal real. Este corte não qualifica esses cenários, PTY, AT, pessoa ou harness/provedor real. Não promove por contagem os 116 cenários completos do plano.

Os antecedentes permanecem separados: duas recusas de gate antes de allocation por uso simultâneo de `stdin=PIPE` e `input=b''`; depois dois cortes de coleta com 438 e 263 nodes conhecidos NÃO EXECUTADOS e cinco erros de namespace `tests`. São erros do runner preservados em `installed-gate-failure.json` e `installed-collection-failure/`. As correções autorizadas foram restritas ao runner: input vazio implica PIPE; adicionar somente a árvore própria ao caminho de helpers, continuando a proibir `tree/src`. Esses antecedentes não foram renomeados como PASS.

Os relatórios por shard incluem snapshots de origem/payload/fonte/helpers, inventário por fase e JUnit sanitizado. Logs capturados e diagnósticos brutos ficam nos Temps próprios, referidos por hashes. A curação final lê apenas esses cortes capturados; mudanças posteriores de frontend/candidato não são confundidas com o código testado no R3.
