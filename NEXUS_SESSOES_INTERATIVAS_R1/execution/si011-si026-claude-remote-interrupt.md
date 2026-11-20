# SI-011, SI-022 e SI-026 — Interrupção remota do Claude

O operador pode confirmar a interrupção do turno Claude exato pelo CLI. O Nexus grava a barreira da fila antes de enviar o controle ao Connector. A revisão depende da geração atual do executor, do evento de geração do terminal e de `nexus-claude-operation-interrupt-v1`. A reorientação tem negociação própria.

O ensaio com Claude 2.1.328 real no Windows e modelo simulado em loopback verificou a recusa antes da geração, com uma revisão de fila antiga e com alvo divergente. Ao simular um Connector com capacidade de reorientação apenas, a revisão de interrupção ficou indisponível e a de reorientação continuou acessível.

O roteiro observou a pausa gravada antes de um único Esc. O turno original ficou `CANCELLED`. A perda simulada da resposta HTTP e a repetição da confirmação recuperaram o mesmo recibo. A fila conservou a mensagem pendente até a retomada explícita. O mesmo processo concluiu a mensagem uma vez, mostrou o resultado ao leitor e foi encerrado pelo controle canônico.

Passaram 111 testes no Core, 136 no Connector e 85 no Nexus, com os wheels instalados. Os dois casos de negociação do Nexus passaram novamente após cobrir a recusa sem a capacidade e a revisão cancelada pelo operador. A validação estrita dos pacotes, os pins e os contratos gerados passaram.

A etapa dispensa migração. A reversão coordenada restaura os commits dos três componentes e os pins anteriores. A qualificação em máquinas separadas e a campanha com provedor real permanecem pendentes. [Evidências e hashes](si011-si026-claude-remote-interrupt.json)
