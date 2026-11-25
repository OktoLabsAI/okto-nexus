# SI-018 server mapping for a managed native session

After fetching the three remotes, the checkouts were clean and synchronized. Nexus `feature/v0.3.8` started this increment at `2708c098` with `origin/main` at `8d77b50c`. Connector `feature/v0.0.14` was at `b360b15` with main at `a3017d9`. Core `feature/v0.0.15` was at `c706d19` with main at `19c99f1`. The consumers pin Core 0.0.15.

The server resolves a managed native identity from its exact canonical scope, the original opening operation and its latest successful or submitted receipt with the same intent hash. The typed internal result retains the native ID, stream epoch, opening operation, adapter, and launch candidate, inventory and profile revisions. It includes the recorded receipt connection and generation separately from the session owner generation. The mapping represents durable opening evidence. A live presenter will also require the current Core owner, lease and authorization.

The existing exact Codex turn target now uses this mapping for its thread match. Its canonical turn proof, queue, capability, and effect revision checks remain in use.

## Evidence and rollback

The focused Python regression passed 99 cases. The synthetic R4 integration checks the retained opening, native ID, stream, launch revisions and receipt provenance. A changed binding, workspace, workspace binding, agent, or owner generation fails the exact lookup. The same suite exercises existing steer, interrupt, and next-turn behavior. Ruff, Git diff validation, offline archive building, and strict Twine checks passed.

This change uses existing durable records and adds no migration. The preceding compatible build restores the prior target lookup while retaining those records. SI-018 remains in progress for the Core runtime ownership proof, current build revalidation, and attachment or saved-session transfer qualification.

## Revalidação no pacote instalado

O CLI instalado abriu o visualizador da sessão Pi selecionada entre
duas sessões vivas do mesmo vínculo. Os três desanexos ficaram ligados
à sessão mais antiga. O PID e o resultado original ficaram disponíveis
até os dois encerramentos canônicos.

Em SQLite somente leitura, o resolvedor do Nexus recuperou os dois
mapeamentos retidos. Cada um conservou a identidade nativa, a época,
a operação de abertura e o build Pi 0.87.1. Dez consultas com vínculo,
workspace, vínculo de workspace, agente ou geração divergente foram
recusadas. A auditoria conservou o hash do banco.

O ensaio usou Pi real com respostas simuladas no Windows. O ledger
registra SI-018 como `IMPLEMENTED` com as provas de propriedade do
Core já arquivadas. SI-T-G01, G16 e G20 conservam a campanha pendente.
O registro dispensa migração. [Dados e hashes](si018-current-native-mapping.json)
