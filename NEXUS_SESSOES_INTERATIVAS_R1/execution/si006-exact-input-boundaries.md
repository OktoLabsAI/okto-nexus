# SI-T-A04, SI-T-A07, SI-T-A09 e SI-T-A10 — Limites da entrada na sessão

O ensaio usou o Pi 0.87.1 e os wheels instalados no executor local do
Nexus no Windows. O projeto era descartável e o provedor, simulado.
[Relatórios e hashes](si006-exact-input-boundaries.json)

- **Escopo exato.** Com o ID da sessão correto e outro executor ou
  vínculo, a conversa retornou HTTP 404 e o envio, HTTP 409. A fila e
  as operações conservaram o estado anterior.
- **Leituras.** Oito consultas à conversa, capacidade, catálogo e fila
  retornaram o mesmo escopo e geração. Não criaram concessões, sessões,
  turnos, filas, decisões ou anexos.
- **Validação de texto.** O servidor recusou mensagens vazias, só com
  espaços e acima de 64 KiB em UTF-8 com HTTP 422. Nenhum desses pedidos
  criou recibo. A única entrada válida chegou ao histórico nativo com
  o texto intacto.
- **Sessão encerrada.** Depois do fechamento canônico, o histórico
  permaneceu legível com HTTP 200. Uma intenção de envio nova recebeu
  HTTP 409. O banco conservou uma sessão e o recibo anterior.

Passaram o ensaio com o Pi e oito testes de armazenamento e
transcript com os wheels instalados. A primeira execução comparou a
estrutura inteira do escopo com o corpo do pedido. A repetição
corrigiu a asserção para conferir também a geração no campo exposto por
cada rota. A auditoria do SQLite confirmou a sessão encerrada, dois
resultados e uma única entrada humana adicional aceita pelo Pi.

Este marco atualiza o ledger e registra evidência. Reverter o commit
remove esse registro, sem migração.
