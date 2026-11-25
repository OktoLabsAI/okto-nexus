# SI-023 · Retomada de contexto salvo no pacote instalado

No Windows, o Connector executou o app-server Codex 0.157.0 com respostas de modelo simuladas em loopback. Com o histórico intacto, o Nexus fechou canonicamente a origem antes de admitir uma sucessora. Cancelar a confirmação deixou o estado intacto. Confirmar chamou `thread/resume` uma única vez para a thread original, e repetir `session resume` recuperou o mesmo recibo. Uma segunda intenção para a mesma origem recebeu HTTP 409.

Com o histórico alterado após a saída do processo, o Connector deixou de registrar a prova de retomada. O Nexus respondeu HTTP 409 e manteve apenas a sessão original já encerrada. A auditoria SQLite confirmou a integridade dos dois bancos, o vínculo da sucessora com o fechamento exato da origem e um único envio produtivo em cada caso. Os dois ensaios terminaram sem processos Codex remanescentes.

Passaram também 41 regressões com os três wheels instalados. Elas cobrem a seleção explícita de sessão, a recuperação pelo recibo original, a recusa de ações de um escritor aposentado e os limites de autorização e histórico dos perfis salvos do Codex e do Claude. Na primeira rodada nativa, a fixture aguardou `ACCEPTED`, estado observado no ensaio do Pi. Os recibos de envio do Codex ficaram em `SUBMITTED`. A repetição restaurou a expectativa original do Codex. [Resultados e hashes](si023-current-saved-contexts.json)

Esta etapa acrescenta evidências ao ledger e dispensa migração. Para revertê-la, basta reverter o commit de evidências. Os ensaios envolveram uma única máquina e zero chamadas a provedores. A qualificação remanescente dos cenários SI-T-G13 a G16 e G20 continua pendente.
