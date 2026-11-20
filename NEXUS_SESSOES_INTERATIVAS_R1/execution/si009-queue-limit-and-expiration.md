# SI-T-B17 e SI-T-B18 — Limite e expiração da fila

Com a fila pausada, a API aceitou 50 entradas e recusou a 51ª com
HTTP 409. As 50 primeiras conservaram a ordem, os recibos e a revisão
da fila. Repetir a primeira intenção devolveu o mesmo recibo.
[Relatórios e hashes](si009-queue-limit-and-expiration.json)

O ensaio adiantou a expiração da primeira entrada no SQLite descartável.
O dispatcher a marcou como `EXPIRED` e manteve o recibo consultável.
As outras 49 conservaram seus dados e acompanharam a nova revisão da
fila. A vaga liberada aceitou a intenção antes recusada com sequência 51.
Ao retomar a fila, a primeira entrega observada foi a da sequência 2.
A entrada expirada continuou sem operação vinculada.

Passaram um ensaio HTTP com SQLite e dispatcher instalados, dois testes
de armazenamento e o Ruff. O primeiro ensaio comparou os itens após a
expiração usando a revisão anterior. A repetição conferiu a revisão nova
e a preservação dos demais campos. O relógio do host seguiu normal.
O adaptador era um peer sintético, sem chamadas a provedores.

O marco acrescenta testes e evidências. Reverter o commit remove essa
cobertura, sem migração.
