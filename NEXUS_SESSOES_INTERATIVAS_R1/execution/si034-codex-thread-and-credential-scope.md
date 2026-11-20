# SI-T-G10 — Escopo do visualizador Codex

O app-server Codex 0.157.0 abriu duas threads sem prompt no mesmo processo. O Nexus instalado ofereceu somente a primeira ao visualizador Codex 0.170.0 em Windows ConPTY. O ensaio usou um catálogo de teste, o broker SQLite do produto e WSS em loopback. A engine recebeu uma credencial sintética exclusiva em um perfil temporário. [Resultados, versões e hashes](si034-codex-thread-and-credential-scope.json)

- O visualizador real leu e abriu a primeira thread. O relay recusou seus pedidos de listar todas as threads e listar as threads carregadas. Um cliente de teste separado confirmou que o mesmo relay também recusa a leitura, a retomada e o histórico da segunda thread.
- O broker encerrou com código 4409 a consulta WSS de histórico para a segunda thread, após uma anexação válida à primeira. O Core também recusou ler a segunda thread pelo identificador da primeira antes de consultar o app-server. Durante as verificações, a engine recebeu apenas sete leituras da thread autorizada.
- O visualizador rodou em um perfil sem credenciais do provedor. A credencial sintética da engine, o identificador da segunda thread, o cookie e o ticket inspecionados ficaram fora da saída de console. Depois de Ctrl+], os modos do console foram restaurados e as duas threads continuaram acessíveis ao próprio dono. O SQLite confirmou três leitores desanexados e zero operações de trabalho.

Passaram a integração com os processos nativos e 76 regressões instaladas de CLI, relay e apresentação remota. A primeira rodada parou na preparação WSS porque o cliente da fixture omitiu os cabeçalhos exigidos do terminal. A repetição usou o cliente do produto. O listener, os processos temporários e a chave TLS foram encerrados ou removidos ao fim.

Esta evidência cobre o ensaio controlado com o par de builds registrado. A campanha com provedor real continua pendente para SI-T-G10. O marco atualiza evidências e ledger e dispensa migração para reverter.
