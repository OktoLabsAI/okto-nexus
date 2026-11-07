## 2026-11-07 — M1 real parcial, interrupção e cleanup pendente

A campanha real consumiu duas admissões: setup concluído e uma solicitação
útil local. O mínimo observado foi 45.843 tokens (22.775 do setup e 23.068 da
thread de trabalho), sem afirmar faturamento final ou corte atômico. O cliente
corrigido recuperou o mesmo perfil por GET, com bytes do perfil inalterados e
sem repetir setup. O Server e o Codex permaneceram nos pacotes originais.

A publicação do arquivo diagnóstico live-accounting falhou com WinError 5
após a persistência crítica do controlador. O runner gravou o fault permanente
CAMPAIGN_RUNNER_EXCEPTION e selecionou interrupt canônico. A mesma operação
útil chegou a CANCELLED/RESOLVED_TERMINAL com uso correlacionado e sem gaps;
não houve report.json, decisão nativa, perda de resposta injetada, continuação
ou execução Connector. O interrupt ficou SUBMITTED/DISPATCHED; seu ACK não é
apresentado como sucesso. Um close canônico separado chegou a SUCCEEDED e a
sessão ficou CLOSED, com o slot próprio liberado. O fault não foi apagado.

A parada normal do Nexus excedeu 45 segundos; mais 120,948 segundos de leitura
mantiveram o mesmo PID 45144, birth e geração. O harness está STOPPED, mas o
drain conserva SESSION_RECONCILIATION_PENDING/CORE_UNKNOWN. O claim do Core
continua pendente; isso não transforma seu recibo de abertura SUBMITTED em
um recibo terminal UNKNOWN. A admissão do serviço está fechada. A tarefa M1
continua registrada; não houve force, kill, uninstall ou limpeza de journals.
A proposta de uma única parada forçada, vinculada à geração, está pronta e
revisada. A autorização adicional foi solicitada porque a v7 excluía force;
nenhuma resposta foi presumida pelo tempo decorrido.

Preparada correção somente da publicação diagnóstica: WinError 5/32 recebe
retry limitado a 80 ms e pode adiar o snapshot público, preservando poll e
parada por orçamento. Erros do checkpoint privado continuam fail-closed.
Passaram dez testes finais, incluindo um bloqueio real de arquivo Windows
com CreateFileW; a rodada inicial de nove foi preservada separadamente. O
runner corrigido ainda não foi executado com provider. O defeito de drain está
sob investigação separada, sem hotpatch no serviço vivo.

DX-T39 passa de NOT_RUN a IN_PROGRESS, registrando esta tentativa incompleta;
nenhum aceite M1 é promovido. A campanha vazia de 24 ações já encerrada é
independente deste serviço M1 ainda pendente. Não se declara medida completa
de instalação até primeiro resultado útil, pois as wheels já estavam instaladas
e nenhum resultado útil foi entregue.
Evidência: `plans/agent_ops/evidence/r3-m1-partial-execution/campaign/summary.json`.
