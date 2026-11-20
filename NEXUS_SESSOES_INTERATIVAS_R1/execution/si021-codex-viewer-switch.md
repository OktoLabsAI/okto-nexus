# SI-T-D13 — Troca de sessão pelo visualizador Codex

O frontend real do Codex 0.170.0 abriu a thread selecionada em um terminal
temporário do Windows. O relay e o servidor Nexus vieram dos wheels
instalados. O contexto nativo apresentado e as duas mensagens nas filas
foram dados de teste. O servidor e o relay escutaram em loopback, com
perfil vazio e sem credenciais de provedor.
[Resultados e hashes](si021-codex-viewer-switch.json)

- O frontend inicializou a thread exata. Ao digitar `/fork` e pressionar
  Enter, ele enviou um `thread/fork`. O relay respondeu `-32601`, e o
  mesmo visualizador permaneceu aberto.
- O teste de integração enviou `thread/resume` com outro UUID pelo
  WebSocket do relay. Recebeu `-32602` e depois leu a thread original
  com sucesso. Também verificou a recusa de `thread/fork`.
- A auditoria consultou o SQLite após fechar o visualizador. As duas
  entradas continuaram em `QUEUED`, com os recibos e as gerações
  originais em seus respectivos executores. Nenhuma operação foi criada.

O teste de terminal e os 70 testes de transporte e contrato passaram.
O teste com o binário real cobre `/fork`. O pedido de troca por
`resume` foi exercitado por um cliente WebSocket de teste. O ensaio
encerrou seus processos temporários e não fez chamadas a provedores.
O cenário qualifica a recusa no gateway local do Codex no Windows.

Este marco amplia a regressão de transporte e atualiza o ledger.
Reverter o commit remove essas evidências e as novas verificações de
teste. Não há alteração de produto nem migração.
