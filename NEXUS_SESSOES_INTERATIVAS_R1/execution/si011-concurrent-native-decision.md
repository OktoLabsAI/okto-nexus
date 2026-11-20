# SI-T-C18 — Uma decisão para a mesma pergunta na Home e no terminal

A rota usada pela Home e o fluxo do terminal chegaram à confirmação da mesma pergunta com respostas concorrentes e identificadores de intenção distintos. O servidor gravou uma decisão e recusou o outro pedido com HTTP 409. A consulta da Home e a recuperação somente leitura do terminal convergiram para o mesmo recibo. O peer recebeu uma única resposta, correspondente à decisão vencedora.

O SQLite registrou uma decisão e um único `input.provide`. A rodada usou a aplicação instalada, HTTP autenticado e um peer nativo simulado dentro do teste. Passaram o caso concorrente e três regressões de recuperação de decisão. O ensaio verifica o contrato consumido pela Home e pelo terminal. A renderização em navegador tem qualificação separada. [Resultados e hashes](si011-concurrent-native-decision.json)

A alteração se restringe a teste e evidência, dispensa migração e pode ser retirada revertendo o commit.
