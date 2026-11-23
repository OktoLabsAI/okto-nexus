# SI-030 · Abrir outra sessão do Pi pelo Connector

No Windows, o CLI instalado abriu o editor do Pi 0.87.1 sobre um executor remoto com Connector R4 autenticado em loopback. A sessão de origem manteve um turno ativo e uma mensagem na fila. Ctrl+O preservou o rascunho e Ctrl+N manteve a anexação original. O servidor recebeu a abertura somente após Ctrl+Y.

A fixture descartou a resposta HTTP após o servidor registrar a abertura. O Connector iniciou o segundo Pi e confirmou o recibo. Repetir a ação recuperou o mesmo checkpoint e mostrou um comando com o ID da nova sessão. O teste executou os argumentos desse comando em outro terminal e comprovou que o segundo editor se anexou ao proprietário nativo correto. O log registrou uma única admissão da nova sessão.

Os processos do Pi tinham IDs distintos. A sessão vazia abriu sem invocar o modelo. A mensagem pendente foi entregue uma vez na sessão de origem. A geração do Connector, a revisão do vínculo e as revisões da autorização foram preservadas. Os dois fechamentos canônicos encerraram os processos e a base passou nas verificações de integridade. [Recibos, hashes e regressões](si030-pi-connector-separate-session.json)

Passaram o ensaio nativo e 80 regressões de CLI, login remoto e apresentação do Pi no pacote instalado. O ensaio usou um modelo simulado com rede desabilitada no Pi. O Nexus e o Connector tinham diretórios isolados na mesma máquina. SI-T-G20 conserva as verificações pendentes de campanha e de plataforma. Esta etapa acrescenta evidências ao ledger e dispensa migração ou reversão de pacote.
