# Verificação da fronteira de reorientação do Pi

No Pi 0.87.1 hospedado, a reorientação comum recebeu o ACK do RPC e apareceu na fila interna enquanto a primeira resposta ainda estava suspensa. Depois de liberar a resposta, o Pi incorporou a mensagem ao mesmo trabalho, antes de `agent_settled`. O recibo do comando de reorientação permaneceu `SUBMITTED` nas duas observações. O evento `message_start` confirmou o consumo da mensagem sintética no ensaio. [Sequências no journal](si025-pi-steer-boundary.json)

Em outro turno da mesma sessão, uma extensão suspendeu o processamento da reorientação. Quando o turno terminou e a extensão voltou, o pin anterior registrou `SUBMITTED` e deixou uma mensagem pendente. A correção confere a identidade do run do Pi no início do RPC e imediatamente antes da inserção na fila nativa. O teste instalado observou a recusa do Pi, fila nativa vazia e o recibo conservador `OUTCOME_UNKNOWN`. O teste unitário também exercitou a chegada de um sucessor enquanto o processamento original aguardava.

Os ensaios usaram o Pi e o Core instalados com provedor sintético, perfil descartável e rede bloqueada no processo do Pi. Passaram 73 regressões do Core, 61 do Connector e o ensaio de edição e fila do Nexus em Windows ConPTY. Para reproduzir, execute a prova com `--hosted-core --hosted-turn --hosted-steer fenced`. Use `baseline` no lugar de `fenced` com o artefato anterior. [Parâmetros do ensaio](si025-pi-native-editor.md)

A etapa dispensa migração. A reversão coordena o commit do Core e os dois pins consumidores. A SI-025 continua em andamento. Falta vincular a intenção confirmada no painel e no terminal ao run observado antes de enviar o RPC e registrar o consumo de fronteira no recibo do operador.
