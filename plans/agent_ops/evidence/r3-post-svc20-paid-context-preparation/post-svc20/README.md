# Connector após SVC20 — preparação offline

Sem seleção ou efeito real. `workflow.json` contém os comandos completos. O seletor futuro só vincula um PASS_SCOPED real e os recibos SVC20 exatos; não inventa DONE, prova de saída ou instalação.

O novo Context preserva `RecoveryContext` e sua tag lifecycle898. Apenas PUBLIC/PRIVATE do Connector passam para `post-svc20`; Nexus continua no contexto original. Cada novo recibo Connector também contém `post_svc20_plan_sha256`. O consumidor pago deve usar `X.base` para Nexus e `X` para Connector, pinando os novos recibos de seleção/watch reais.

Antes do único daemon start: DONE/reuse_existing/epoch2, rotação ligada, task instalada habilitada/inativa com digest igual, três exits de ambas as coortes SVC20, migração exata, ausência canônica, Nexus READY observado, epoch2 atual e contadores/grants iguais ao baseline zero. A reserva é durável antes do Popen e há segunda revalidação; falha consome a seleção sem replay. Não há install nem recibo de install no novo namespace.

A captura exige geração/ciclo novos antes de publicar owner-selection. O watcher e cleanup reutilizam funções congeladas query/synchronize, sem force. Stop/uninstall escrevem somente novos recibos, preservando os antigos. Após uma admissão paga separada, cleanup não exige zero operações histórico; a reconciliação de trabalho continua responsabilidade do runner pago, sem inferir settlement por saída física.

Nove testes focais passaram em 3,92s com fixtures e SQLite sintético. Nenhum serviço, HTTP, Scheduler, provider ou credencial real foi acessado. O runtime-freeze inclui next_connect.py antes do import dinâmico. Originais R e SVC20 foram preservados.

Limite herdado: os 45s pertencem ao CLI do produto. O wrapper usa `child.wait()` sem prazo próprio e permanece junto do filho se ele atrasar; não promete duração total finita, não mata o processo nem repete a seleção. O root mantém o handle da execução para observação e eventual reconciliação.
