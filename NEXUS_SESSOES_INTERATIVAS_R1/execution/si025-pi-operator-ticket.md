# Acompanhamento local do Pi com ticket de operador

O Nexus disponibiliza `session attach` em modo de leitura para sessões embutidas do Pi 0.87.1 abertas com o build Windows x64 revisado. A composição usa a opção existente `runtime_session_interaction_enabled` em conjunto com a integração de harnesses. Ela exige a identidade portátil do Node, do Pi e da cadeia de dependências observada no ensaio. Sessões abertas pelo RPC comum e sessões de outros builds ficam fora dessa capacidade.

O broker existente emite o ticket e o vincula à sessão, ao login e ao protocolo do Pi. O ticket só pode ser usado uma vez. O cliente recebe a confirmação `attached` depois que o renderer aceita a conexão. A saída filtrada circula em quadros binários. O Nexus revalida o login e a capacidade também durante a ociosidade e encerra a visualização em caso de revogação. O terminal recebe somente saída, e o Ctrl+C fecha o cliente local.

Os testes cobrem reutilização de tickets, protocolo de outro harness, recusa de escrita e retomada salva, perda de autorização, falha de abertura e saída binária sobre TCP em loopback. O ensaio em Windows ConPTY consumiu o fluxo do broker com renderer simulado e confirmou detach por Ctrl+C, restauração dos modos do console e ausência de uma operação de runtime. Separadamente, o ensaio do Pi real com provedor sintético usou a composição do host e o build selecionado, mantendo o processo e o turno ativo durante a troca de visualizador. [Resultados e artefatos](si025-pi-operator-ticket.json)

Os dois ensaios passaram com os wheels instalados. Também passaram 88 testes de regressão com os artefatos instalados, incluindo rota, CLI, broker, lifecycle do host e OpenAPI.

O ensaio do Pi real pode ser repetido com `python NEXUS_SESSOES_INTERATIVAS_R1/execution/si025-pi-observer-probe.py --node <node.exe> --pi-release <raiz-do-release> --hosted-core --hosted-turn`. Use o wheel do Nexus e o pin do Core registrados na evidência. Os testes do broker e do cliente ficam em `tests/session_interaction/test_presentation_transport.py` e `tests/session_interaction/test_session_cli.py`.

A alteração dispensa migração e pode ser revertida no Nexus em um commit. A SI-025 segue em andamento. A etapa seguinte é qualificar em conjunto o terminal, o ticket e o Pi real e ligar a entrada à fila, às revisões e às ações de aprovação existentes.
