# Abertura confirmada de uma sessão vazia

Ao pedir o visualizador em uma conexão sem sessão viva, o Connect oferece separadamente a abertura de uma sessão vazia. Exibe a política vigente e usa Não como padrão. O servidor confere o grant do agente no momento da admissão e volta a verificá-lo no despacho. Uma recusa orienta a revisar a autorização pelo comando existente `work authorize`.

A abertura usa apenas a operação canônica `runtime.open`. O CLI registra a intenção antes da requisição e confere o recibo antes de anexar. Após perda de resposta, recupera essa mesma intenção. Uma admissão já registrada evita outro POST. Uma intenção sem admissão pode continuar com o mesmo ID após confirmação. O checkpoint de abertura fica separado de `work resume`.

Com o executável instalado em Windows ConPTY e Pi 0.87.1, Enter manteve a conexão sem sessão. Após confirmar com grant vencido, o servidor recusou antes de gravar uma operação ou criar a sessão, preservando a conexão e o grant. Em seguida, a fixture concedeu autorização válida pelo fluxo canônico e o CLI abriu uma única sessão vazia. O visualizador abriu a sessão exata e Ctrl+C devolveu o shell. O SQLite confirmou um detach, o fechamento canônico, zero turnos, zero resultados e zero checkpoints de trabalho. [Dados e hashes](si029-empty-session-opening.json)

Passaram 40 regressões com o pacote instalado e sete verificações focais em código-fonte. A prova de perda de resposta usa injeção no cliente. A integração usa a instalação real do Pi, um login humano temporário com cofre de teste e rede externa bloqueada. O marcador de início do visualizador mede a entrada no terminal antes do Ctrl+C. Campanhas com provedores e a qualificação entre hosts continuam pendentes.

O marco dispensa migração e alterações de pins. O rollback consiste em reconciliar os recibos de abertura em andamento, reverter o commit e restaurar o wheel anterior.
