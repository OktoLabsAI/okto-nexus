# SI-022 e SI-032 · Expiração do escritor remoto do Claude

O leitor e o escritor remotos renovam a apresentação quando enviam o sinal de aplicação. Um ping do WebSocket recebe resposta e deixa o prazo da apresentação intacto. Quando o prazo vence, o broker retira o visualizador e libera a escrita. Os testes de transporte exercitam as duas permissões e recuperam a entrada do escritor pela mesma intenção após a expiração. [Regressão](../../tests/execution_r4/test_remote_claude_presentation.py)

No Windows, o Claude Code 2.1.328 gerenciado pelo Connector tinha um turno em execução. A API da Home e um escritor WebSocket registraram duas mensagens para turnos seguintes. O escritor enviou um sinal de aplicação, depois ficou em silêncio após um ping. O relógio controlado avançou apenas no broker de apresentação. O prazo venceu, o socket fechou e a entrada permaneceu na fila. A conexão do Connector, a concessão de execução e o processo Claude foram preservados.

O CLI instalado reanexou a escrita em ConPTY sem pedir transferência. O turno original terminou nesse período. O mesmo processo recebeu as mensagens da Home e do terminal nessa ordem. A auditoria confirmou três resultados, uma abertura nativa, um fechamento canônico, o recibo original e a integridade dos bancos. [Resultados e hashes](si022-claude-silent-writer.json)

Passaram 49 regressões de transporte nos wheels instalados e a integração nativa. Os ensaios usaram Connector e Nexus nesta máquina, com respostas determinísticas em loopback. O gate de campanha de SI-T-G08 segue aberto. Este marco acrescenta testes e evidências. Dispensa migração e pode ser revertido pelo commit do Nexus.
