# SI-009 cancel one owned input

The cancellation boundary uses the active human login fence and the exact
input author, surface, session scope, owner generation and current
cancellation capability. Both input and queue revisions participate in
the CAS. Only QUEUED and PAUSED rows without a linked operation or possible
effect can become CANCELLED. The original content and history, queued
successors and current runtime work are preserved.

An existing PREPARED capacity attempt remains durable when cancellation
wins, and SI-008 can release the fenced reservation by its original ID.
When R4 staging wins, cancellation is refused. The action does not need
a productive execution grant.

Thirteen fixture cases cover current login, two logins for the same
operator, stale scope and revisions, eligible states, and both SQLite
writer outcomes in the staging race. No schema change. Public HTTP and
the queue UI remain pending.

## Revalidação no pacote instalado

Passaram 22 casos com o candidato `8bcee9bd` no Windows. Os testes HTTP
confirmaram a listagem paginada, o cancelamento isolado e as duas ordens
da disputa com o dispatcher. Quando o cancelamento venceu, o item ficou
registrado como `CANCELLED`, sem operação vinculada. Quando a reserva já
havia sido consumida, o cancelamento devolveu HTTP 409 e o texto original
seguiu uma vez. Nos dois casos, o item seguinte foi entregue na ordem
esperada. Nenhuma operação de interrupção ou encerramento foi criada
pela ação de cancelar.

O teste de fila cheia preservou o conteúdo aceito, expôs a expiração e
liberou a capacidade após o prazo. A bateria atual usou um peer sintético.
O ensaio com Pi instalado, respostas simuladas e turno original preservado
mantém seu próprio candidato. Este marco é reversível pelo commit e
dispensa migração. [Resultados e hashes](si009-current-cancellation.json)
