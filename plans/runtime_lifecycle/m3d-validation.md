# M3d — presença local vinculada ao owner

O gate real M3c mostrou agentes locais online com “Last contact: never”.
O host embedded não atualizava esse campo e a projeção confiava em
`CONTROL_READY` persistido, mesmo se a autoridade daquele owner tivesse expirado.

Agora o claim inicial registra contato, e cada heartbeat confirmado atualiza
o contato do executor embedded na mesma transação da renovação do owner.
Somente a identidade corrente atualiza seu executor; heartbeat rejeitado não
altera o contato. A consulta de presença exige correspondência com o owner
atual e lease ainda válida. Dados de agente e histórico de mensagens não
substituem essa evidência. A mesma projeção atende Agents, Graph e descoberta
pelas ferramentas, sem modificar permissões ou a autorização de execução.

Validação em 2026-10-16: **46 casos distintos aprovados**, tanto em source
quanto na wheel instalada em ambiente isolado. A campanha instalada verificou
os bytes dos três pacotes e encerrou com `changed_inputs=[]`, sem falhas,
erros ou skips. Inclui presença por API/Graph/MCP, estados remotos existentes,
expiração exata, owner ausente/substituído, pausa do processo local,
rollback do heartbeat e retomada sem permitir que o owner cercado reapareça.

Evidência: `m3d-results.json`. A instalação global continua no M3c validado
pela interface. Não foi feito outro restart do usuário apenas para esta
correção intermediária; o próximo grande gate real deve conferir esse tooltip.
O M3 completo permanece aberto, incluindo isolamento do inventário e falhas
de renovação remotas por sessão. O descompasso de ACK acessível de L6 não
reapareceu no M3c; não foi declarado corrigido por esta mudança.
