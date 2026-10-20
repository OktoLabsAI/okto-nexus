# M3g — Repor aquecimento recusado antes do Core

## Incidente

Na geração global 70, o Pi recuperou READY, mas quatro reservas de aquecimento
ficaram STARTING. As sessões estavam FAILED/NONE, sem recibos Core. A recusa
durável de despacho era RESOLVED_TERMINAL, possible_effect=false, stage=dispatch:
`The dispatch inventory is no longer fresh.` O inventário perdeu a validade
antes do envio. A manutenção reconhecia fechamento confirmado ou recibo Core
de falha sem efeito; essa recusa anterior ao Core não possui tal recibo.

O Pi respondeu ao teste pela UI usando capacidade adicional, sem restaurar as
quatro vagas aquecidas. O erro não era uma nova falha compartilhada do host.

## Correção

A manutenção do pool reconhece a recusa da abertura exata, com operação e
despacho terminais, sessão FAILED/NONE e sem stream, publicação ou recibo Core
da sessão. O registro precisa identificar a mesma operação, etapa dispatch e
booleano possible_effect=false. FAILED/NONE sozinho nunca libera capacidade.

Essa prova libera somente a reserva lógica não utilizada. Mantém sessões e
operações no histórico e deixa o aquecimento usar os mecanismos existentes de
backoff e reposição. Não altera o prazo de validade do inventário, as verificações
de autorização ou os recibos, nem reenvia a operação recusada. A política é
compartilhada por pools locais e remotos no Nexus; Core e Connector não mudam.

## Validação

Os testes reproduzem a recusa antes do Core e exigem reposição automática do
pool nos adaptadores Pi, Claude e Codex, sem abrir as sessões recusadas.
Evidências contraditórias — lease ativo, stream, efeito incerto, despacho ainda
em andamento, outra identidade, recibo ou publicação — devem impedir liberação.
Resultados finais e limites de implantação são registrados no ledger.

Os testes com peers determinísticos não qualificam um provedor real. A leitura
do banco global confirmou que as quatro reservas atendem à prova estrita, sem
editar dados ou forçar sua liberação. A causa do custo da atualização inicial
do inventário permanece no plano de prontidão por harness; este checkpoint
impede que uma recusa transitória deixe a capacidade lógica presa.
