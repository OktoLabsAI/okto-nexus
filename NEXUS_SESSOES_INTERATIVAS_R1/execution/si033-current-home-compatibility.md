# SI-033 · Home e fluxos existentes no pacote instalado

O ensaio no Windows usou Nexus 0.3.8, Connector 0.0.15, Core 0.0.16, Edge e Pi 0.87.1. Os testes de Python conferiram que os três módulos vieram da instalação dos wheels. O Connector operou em loopback com um executor remoto e o Pi usou duas respostas sintéticas. [Versões, hashes e resultados](si033-current-home-compatibility.json)

1. A Home registrou uma mensagem canônica antes de existir uma sessão. Ao abrir a conversa, o Edge mostrou o texto do pedido.
2. O comando de anexação abriu o editor da sessão exata em Windows ConPTY. Com o primeiro turno retido, a mensagem do terminal ficou em `QUEUED`, sem uma operação de execução. O detach liberou a anexação enquanto o processo original do Pi permanecia ativo.
3. No Edge, a mesma sessão reabriu pelo endereço original. O harness continuou em **Working**, em uma única região com **Active**, **Needs you** e **Results**. A mensagem do terminal entrou na conversa depois da primeira resposta e antes da segunda. As duas respostas apareceram uma vez cada.
4. A base confirmou uma sessão do executor remoto, uma abertura, dois turnos, um encerramento canônico e dois resultados. A mensagem do terminal alcançou `ACCEPTED_NATIVE`. As verificações de integridade e chaves estrangeiras passaram.

Passaram 216 regressões instaladas para as entradas legadas do CLI, `--no-chat`, perfis existentes, recuperação por recibo, navegação de handoffs e o ciclo de participant. Os 50 testes Node incluíram a região única da Home, o sino global, os quatro destinos principais e Advanced, com os IDs existentes. O pytest registrou avisos de depreciação nas dependências Starlette e websockets.

O ensaio anterior de duas abas observou, em separado, as transições da fila, o steer consumido e os cards em Results. Os cenários SI-T-I01 e SI-T-I04 continuam `NOT_RUN` para a campanha exigida. A avaliação humana e o leitor de tela permanecem no gate da SI-036. [Projeção de estados em duas abas](si036-home-states-native-detach.md)

Este marco atualiza o ledger e as evidências. O rollback é reverter o commit de evidências e dispensa migração de dados. A etapa seguinte é SI-034, segurança e revogação ponta a ponta.
