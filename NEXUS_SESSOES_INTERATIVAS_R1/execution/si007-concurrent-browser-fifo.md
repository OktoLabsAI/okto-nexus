# SI-T-B02, SI-T-B03, SI-T-B04, SI-T-B05 e SI-T-B11 — Fila com duas abas

Duas abas no Edge usaram logins independentes da mesma conta
descartável. Ambas abriram a conversa exata de um Pi 0.87.1 no executor
local do Nexus. O turno original continuou ativo enquanto a fixture
segurava a primeira resposta do provedor simulado.
[Relatórios e hashes](si007-concurrent-browser-fifo.json)

1. Dois pedidos chegaram juntos à fronteira HTTP. O servidor atribuiu
   sequência 1 a B e sequência 2 a A. A primeira aba enviou C depois e
   recebeu a sequência 3.
2. Cada envio recebeu HTTP 202 e mostrou a confirmação de fila na Home.
   O SQLite registrou três recibos ainda sem operação vinculada, dois
   autores de sessão e só o turno original aberto.
3. As duas abas fecharam antes de liberar a resposta original. O
   dispatcher entregou B, A e C, com uma operação por entrada. Cada
   resposta ficou retida até conferir que os itens seguintes
   continuavam na fila.
4. O histórico do Pi preservou os três textos, inclusive a quebra de
   linha e o acento. A auditoria confirmou quatro resultados e apenas
   uma sessão, encerrada pelo controle canônico.

Passaram o ensaio com Edge e Pi, a auditoria SQLite e dois testes de
armazenamento com os wheels instalados. A primeira checagem do navegador
consultou o cookie pelo caminho raiz. A repetição consultou o caminho
da API, onde o Nexus limita o cookie, e usou a mesma sessão do Pi.
A barreira de concorrência e o provedor eram fixtures descartáveis.

O marco atualiza as evidências e o ledger, sem migração. Reverter o
commit remove o registro.
