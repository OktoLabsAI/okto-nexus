# SI-026 — Identidade da sessão Claude no terminal mantido pelo Core

O Core pode confirmar que o terminal aberto no Windows retomou o UUID gravado no histórico. A verificação cruza o registro local do Claude 2.1.328 com o PID e o instante de criação do processo obtidos pelo handle do Windows Job. Ela também verifica o diretório de trabalho, o diretório de estado e o estado ocioso do terminal. Divergência, registro instável ou saída do processo recusam a verificação.

No ensaio com o Claude real e o Core instalado, o terminal exibiu o histórico antes de receber a primeira entrada. A verificação aceitou o processo mantido pelo Core e recusou outro UUID e o mesmo PID com outro instante de criação. A entrada seguinte usou a mesma conversa, terminou após a saída do leitor e gravou `SUCCEEDED`. O modelo foi simulado em loopback. O ensaio encerrou os processos temporários. [Cenários, revisões e hashes](si026-claude-terminal-owner.json)

Passaram 62 testes do Core instalado, três de retomada Codex do Nexus com o Core atualizado e 122 do Connector instalado. Um teste de parada supervisionada do Connector retornou `unconfirmed` onde esperava `drained`. O mesmo resultado foi reproduzido com os wheels anteriores.

SI-026 continua em andamento. O próximo passo é usar a verificação durante a abertura canônica da sucessora e vincular a configuração efetiva e a aposentadoria da origem à admissão. A qualificação dessa abertura, dos anexos e dos controles de turno permanece pendente. O marco dispensa migração. O rollback restaura os commits e os wheels anteriores nos três repositórios.
