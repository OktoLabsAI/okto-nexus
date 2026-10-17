# M4c — Checkpoints de liberação local

Checkpoint concluído: **44 testes passaram na wheel final instalada**, sem falhas, erros ou skips; entradas inalteradas durante a campanha. A migração 144 acrescenta um checkpoint terminal e uma revisão
de obrigações à sessão canônica. Sessões existentes começam sem checkpoint:
o estado CLOSED/FAILED e os antigos flags de publicação não são tratados como
prova suficiente de liberação.

O caminho de aposentadoria verifica a prova do Core, geração e abertura exatas,
stream único e watermark comprometido; aguarda produtores da sessão e limpeza
de ferramentas, publica os últimos receipts e só então grava o checkpoint junto
com a retirada das pendências. Recusas de abertura usam sua prova específica,
sem fabricar encerramento de processo. A limpeza de credenciais também precede
o checkpoint dessa recusa.

Operações/publicações, receipts, streams, eventos, watermarks e alterações de
identidade/estado relevantes invalidam o checkpoint na transação correspondente.
A revisão impede que uma obrigação surgida entre a observação e o commit seja
ocultada. Uma reserva física ainda ocupada no ledger Core invalida o checkpoint
no startup e exige recuperação; o registro Server nunca libera esse recurso.
Observadores concorrentes preservam o primeiro checkpoint equivalente.

A recuperação e a publicação de eventos dispensam reabrir journals já
verificados. A aposentadoria de histórico usa lotes de até 128 sessões, com
progresso durável por sessão. Consulta e atualização de publicações pendentes
usam índices parciais, incluindo o escopo exato da sessão.

Testes adicionados: rollback atômico, provas incompatíveis, geração obsoleta,
invalidação transacional, nova obrigação entre prova e checkpoint, retomada
após interrupção no item 65 de um histórico de 300 sessões, três adaptadores
com Core real e adaptador nativo determinístico, ledger ocupado contradizendo
checkpoint, falha de limpeza de ferramentas e resposta perdida após checkpoint.
As medições sintéticas de 1k/10k/100k cobrem consultas e a transação de
aposentadoria; não representam execução de provedores reais.

Durante o desenvolvimento, uma comparação após reinício revelou regravação
equivalente do checkpoint por dois observadores. A idempotência foi corrigida;
o teste mantém a exigência de preservação exata do registro e de não reabertura
do journal. A revisão também moveu o checkpoint de recusa para depois da limpeza
de ferramentas. A campanha ampliada encontrou ainda três falhas no reparo de
entregas incompletas: remover sua projeção de liberação deixava o checkpoint
válido e impedia a reconstrução. A migração agora invalida o checkpoint ao
remover/alterar essa evidência. O teste anterior permanece e foi ampliado para
verificar rollback e invalidação; os três adaptadores passaram na reprodução
com source corrigido. Artefatos intermediários não qualificam a fronteira final.

Limites: a inicialização ainda enumera o catálogo de arquivos/sessões completo,
com o teto histórico anterior. Recusas iniciais sem stream e sessões nunca
despachadas ainda seguem sua prova anterior sem checkpoint terminal novo.
Remover essas varreduras/teto, concluir o backfill inicial e a auditoria fora da
admissão, e garantir orçamento/justiça entre streams continuam no M4. A criação
de índices é uma migração SQLite atômica, não uma migração de schema em lotes.
Esta etapa não foi aplicada à instalação global e não tem novo gate de UI.

Acompanhamento pela UI da instalação M3c: Agents permaneceu LIVE, com Pi,
Claude e Codex locais ONLINE; o Pi exibiu 4/5 instâncias disponíveis.
Imagem local: `build/runtime-lifecycle-m3c-live/agents-during-m4c-validation.png`.
Essa observação não representa execução do M4c na instância em uso nem substitui o
próximo gate integrado; nenhuma nova mensagem foi enviada nesta observação.


## Qualificação final

Wheel: `build/runtime-lifecycle-m4c-verified-dist/okto_nexus-0.3.1-py3-none-any.whl`.
SHA-256: `5ea91e2a0cb64a77a5b9c5b7dfd3ef4525fd695690154db95a40c7e0d6bb00ac`. Os 527 arquivos Python/SQL da wheel
conferem com o checkout. O runner também conferiu os bytes instalados de Nexus,
Core e Connector, sem substituir o pacote instalado pelo source da aplicação.

Foram executados todos os casos de `test_local_retirement.py`,
`test_local_pending_queries.py`, `test_embedded_preopen_fences.py` e os três
adaptadores de `test_released_incomplete_turn_does_not_block_next_message`.
O rollback da remoção de uma liberação preserva o checkpoint; o commit o invalida
e a recuperação reconstitui a liberação sem executar novamente a tarefa.

A campanha exploratória anterior teve 123 casos aprovados e três falhas, todas
nessa última fronteira corrigida. Houve alterações de entradas durante aquela
campanha: ela não qualifica a wheel final. Seus resultados e limites permanecem
registrados separadamente, sem somar contagens como se fossem uma única campanha.

Relatórios finais: `build/runtime-lifecycle-m4c-verified-installed/` e
`m4c-results.json`. O planejamento do trabalho restante está em `m4d-design.md`.
M4 permanece em andamento; esta evidência não encerra os gates UI-A/B/C.
