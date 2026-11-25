# SI-022 · Retomada após perda abrupta do WebSocket

O corte do WebSocket do Connector chegou ao Server pelo ASGI com o código 1005. O wheel anterior descartava a prova de retomada mesmo com um vínculo autenticado e válido. A correção reconhece esse evento como perda de transporte. A prova depende do ticket ativo, da geração do vínculo e das revisões de autorização. O caso de regressão falhou no wheel anterior e passou no corrigido.

No Windows, Server e Connector compartilharam a máquina e o Connector hospedou o Pi 0.87.1 em um subprocesso. O ensaio cortou o canal de controle durante um turno, reteve a prova até o fim da janela de retomada e observou a saída do processo antes de a nova geração ficar pronta. O resultado original foi recuperado como `SUCCEEDED`. A entrada enfileirada permaneceu em `BLOCKED_SESSION` na sessão original, com o mesmo ID e sequência. Um novo pedido explícito abriu outra sessão e outro processo, executou um turno e encerrou normalmente. O teste usou respostas sintéticas e zero chamadas a provedor. [Resultados, versões e hashes](si022-current-native-reconnect.json)

A alteração é de código e pode ser revertida no Git. A validação entre máquinas separadas, SI-T-H01, fica para uma etapa posterior.
