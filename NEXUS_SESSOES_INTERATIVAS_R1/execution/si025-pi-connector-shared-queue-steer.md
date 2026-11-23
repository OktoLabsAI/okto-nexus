# SI-025 · Fila e reorientação na mesma sessão do Pi pelo Connector

No Windows, o editor em ConPTY e a API autenticada da Home registraram mensagens para o próximo turno enquanto o Pi 0.87.1 estava ocupado. Os dois pedidos partiram juntos e receberam entradas distintas na mesma fila. A repetição da intenção HTTP devolveu o recibo original.

O operador revisou a reorientação no editor com Ctrl+R e confirmou com Ctrl+Y. O recibo vinculou a reorientação ao turno ativo. Esteve em `awaiting_boundary` até o Pi consumir a orientação e mudou para `applied`. As duas entradas comuns conservaram seu estado e sua posição na fila durante a reorientação.

O editor desanexou enquanto o turno original continuava. Depois do seu término, o Connector entregou as duas entradas em ordem FIFO. O histórico nativo mostrou uma ocorrência de cada mensagem de usuário. O transporte registrou um `steer` e três `prompt` no mesmo processo. O fechamento canônico encerrou o Pi e as verificações de integridade do banco passaram. [Recibos, artefatos e testes](si025-pi-connector-shared-queue-steer.json)

Passaram o ensaio nativo e 98 regressões de fila, apresentação e CLI com os pacotes instalados. O Nexus e o Connector usaram diretórios separados em loopback. A fixture acessou a API HTTP diretamente e usou um modelo simulado com rede bloqueada no Pi. SI-T-G18 conserva a qualificação pendente em campanha. Esta etapa registra as evidências no ledger e dispensa migração ou reversão de pacote.
