# SI-017 exact conversation stream

The dashboard follows an authenticated, exact-session SSE feed of committed cursor changes. The feed publishes the stream epoch, contiguous position, and gap state. The existing bounded transcript endpoint still projects the messages. The browser reads from its current cursor after a change and keeps periodic capability and receipt reads. If the stream is unavailable, it resumes bounded transcript polling. A foreign scope, replaced owner, or revoked login cannot continue the previous stream.

The conversation keeps its rendered message identities and input state during committed updates. A reader above the newest message receives a single New messages control and can choose when to jump. History pagination stays explicit and a queued Load more click survives a snapshot already in flight.

## Evidence

- 99 Python tests passed. The stream tests check unchanged positions, cursor advancement, login revocation before another frame, and bounded termination reasons. The runtime integration verifies that wrong workspace, stale owner generation, and extraneous query fields cannot open the stream.
- 417 frontend tests passed, including the position and owner validation. TypeScript and Vite, focused Ruff, the offline lock check, Git diff checks, and strict archive checks passed.
- Headless Edge connected over SSE to an isolated Uvicorn dashboard with a synthetic Codex peer. The idle view did not reread the transcript. Five new deltas were rendered after one bounded read beginning at the existing cursor. The draft, textarea focus and selection, and earlier transcript scroll position stayed intact. The New messages control jumped to the latest output, and revoking the fixture operator login cleared the panel. This run exercises browser behavior with synthetic data. It does not qualify the native harness, operating-system IME, or screen reader.

## Delivery and rollback

The new endpoint is read-only and adds no migration. Rollback restores bounded periodic transcript reads. The existing queue, receipts, transcript storage, and Core and Connector pins remain compatible. SI-017 remains in progress for cross-session navigation and the remaining keyboard, zoom, pause, and assistive technology checks.

## Revalidação e gate G2

O Edge, com os wheels instalados no Windows, abriu a conversa exata de
uma cópia descartável antes de cada perda de acesso. O vencimento
da sessão de operador produziu HTTP 401. A retirada de acesso em
outro ensaio produziu HTTP 403. Em ambos, o histórico e o painel
protegidos saíram da interface. Após restaurar a autorização do
segundo ensaio, um navegador limpo reabriu a conversa original.
Os 69 eventos, três resultados e quatro operações ficaram intactos.

As primeiras montagens pararam ao reabrir a interface após o 401.
A repetição usou perfis de navegador independentes para os dois
cortes e a restauração. Os ensaios de IME, zoom, foco, pausa visual
e fala do Orca conservam as evidências dos seus ambientes.
A fala no Windows e o aceite do participante ainda fazem parte
da qualificação pendente.

SI-012 a SI-017 verificam o ciclo G2 da conversa, fila e controles
pela Home. O ensaio do compositor confirmou o papel de usuário
nativo e zero entregas pelo barramento Operator. Este registro
dispensa migração e pode ser revertido pelo commit.
[Revalidação e escopo](si017-current-navigation.json) [Envio pela Home](si013-current-composer.json)

## Atualizações ao ler histórico paginado

O painel agora mostra **New activity is available** quando o cursor validado avança além do histórico carregado e ainda há páginas a ler. Páginas que já existiam ao abrir a conversa ficam silenciosas. O aviso usa a região de status existente, preserva foco e rolagem e desaparece quando a leitura alcança os eventos novos.

No Edge para Windows, o pacote anterior recebeu os eventos no stream sem mostrar o aviso. O novo wheel exibiu um aviso em cada cenário, com 24 e 54 fragmentos sintéticos. No caso maior, o aviso continuou visível depois do primeiro clique em **Load more messages** e desapareceu após o segundo. O navegador consultou o histórico seguinte somente após cada clique. A primeira tentativa do caso maior precisou ajustar a paginação da leitura de verificação da API.

Passaram 423 testes do frontend, 29 de transcrição e stream, as checagens do wheel e do sdist e a verificação de integridade das cópias descartáveis do SQLite. O ensaio cobre a região de status e o foco no navegador. A validação de fala no Windows segue pendente. A alteração dispensa migração e pode ser revertida pelo commit que atualizou o componente e o bundle. [Resultados e hashes](si017-paged-live-updates.json)
