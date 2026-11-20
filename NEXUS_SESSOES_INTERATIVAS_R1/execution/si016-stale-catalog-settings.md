# SI-T-D10 — Catálogo antigo após alteração de configuração

O Edge abriu `/send` na conversa exata de um Codex 0.157.0 em execução.
Os três wheels instalados serviram a Home e a API. O Connector usou
R4 em loopback e o app-server recebeu uma resposta simulada.
[Comandos, hashes e observações](si016-stale-catalog-settings.json)

1. Um segundo cliente autorizado pausou a fila e o catálogo mudou de
   revisão. O navegador ainda tinha a revisão anterior. Ao confirmar
   `/send`, recebeu HTTP 409 e preservou o rascunho. O servidor conservou
   a revisão da fila e registrou zero novas entradas e operações.
2. Atualizar os comandos preservou o texto. Uma confirmação explícita
   com a nova revisão obteve HTTP 202 e registrou uma única entrada na
   fila pausada. O Codex concluiu o turno original. A mensagem da fila
   ficou sem operação nativa e apareceu como `BLOCKED_SESSION` no
   recibo após o fechamento da sessão.
3. Uma alteração dos metadados do agente descartável via API avançou a
   revisão de configuração e preservou a revisão de autorização. O
   comando `/status` com a revisão anterior recebeu HTTP 409. O comando
   atualizado recebeu HTTP 200 e indicou a mesma sessão fechada.

Passaram o ensaio no navegador, quatro testes de API instalados e 20
verificações de componentes. O primeiro roteiro tentou acessar a janela
pelo processo de automação. Corrigi o acesso e reabri a mesma conversa
enquanto o turno original ainda estava retido. O SQLite e o journal
confirmaram um lançamento do app-server, um resultado e uma entrada
preservada sem despacho. Houve zero chamadas a provedores externos.

O ledger registra `PASS` para SI-T-D10. A alteração acrescenta evidências
e dispensa migração. A reversão usa o próprio commit.
