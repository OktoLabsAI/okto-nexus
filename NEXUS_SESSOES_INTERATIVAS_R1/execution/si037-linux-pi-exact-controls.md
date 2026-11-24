# SI-025 / SI-027 / SI-031 / SI-037 · Controles do turno do Pi no Linux

O Nexus e o Core qualificam reorientação e interrupção para a instalação exata revisada do Pi 0.87.1 com Node 24.15.0 em Linux x64. A API só apresenta esses controles quando a sessão e o canal atuais atendem às verificações de autoridade. A confirmação continua vinculada ao turno, à revisão da fila e à geração do dono da sessão. [Identidades e artefatos](si037-linux-pi-exact-controls.json)

Os ensaios usaram os wheels instalados, um Connector real por R4 e o CLI em pseudoterminal no Ubuntu 24.04.5 em WSL2. Cada cenário abriu uma sessão explícita e iniciou um turno controlado. O editor exibiu a revisão. Ctrl+N cancelou sem registrar um controle e Ctrl+Y confirmou uma nova revisão do mesmo turno.

- **Reorientação.** O editor mostrou que o pedido aguardava a fronteira e, depois, que o Pi o aplicou. O histórico contém a solicitação original e uma única ocorrência do rascunho. O Nexus registrou uma submissão e uma reorientação para aquele turno.
- **Interrupção.** O editor confirmou a interrupção e a pausa da fila. A mensagem seguinte permaneceu enfileirada no escopo original. O histórico contém apenas a mensagem do turno interrompido e o provedor simulado recebeu uma única chamada.

Nos dois casos, Ctrl+] restaurou o terminal, manteve o mesmo processo e a mesma sessão, e permitiu o encerramento pelo comando canônico. O cofre usa uma fixture para o operador temporário. O Pi real recebeu respostas simuladas com saída externa bloqueada. A distribuição descartável do WSL e seu disco foram removidos.

Passaram os dois ensaios integrados e 314 execuções de regressão. Três dessas execuções confirmam o reparo da fixture de apresentação remota, que referenciava o seletor anterior. As tentativas preliminares também registraram troca de geração do Connector durante a abertura automática e uma expectativa incorreta sobre o envelope do primeiro prompt no histórico. Os ensaios finais usaram a abertura explícita e o recibo `ACCEPTED` do turno. A observação de troca de geração fica registrada como limite da abertura automática exercitada. [Resultados e hashes](si037-linux-pi-exact-controls.json)

Retomada do histórico salvo e comandos literais no Linux ainda exigem qualificação. O ledger mantém os cenários de campanha pendentes, inclusive o ensaio em outra máquina e a aceitação humana. O marco dispensa migração. Para revertê-lo, reverta o seletor no Nexus e o registro no Core e restaure os pins anteriores nos dois consumidores. O próximo ensaio local é retomar a sessão pelo histórico salvo após o fechamento canônico.
