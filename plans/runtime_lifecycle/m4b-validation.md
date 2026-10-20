# M4b — Consultas de publicações pendentes

Checkpoint concluído: 60 testes da wheel instalada passaram, sem falhas, erros
ou skips, com `changed_inputs=[]`. Core e Connector continuam nos artefatos M3e.
A migração 143 cria índices parciais sobre os flags
duráveis `terminal=0` e `drained=0`. Não há uma segunda lista mutável de pendências:
o SQLite mantém a participação no índice na mesma transação do registro.

As publicações são consultadas a partir das pendências, com associação exata à
operação quando há filtro por agente. Isso elimina a materialização dos IDs de
todo o histórico do agente. Os streams ativos usam o predicado explícito que
permite utilizar o índice parcial. Recuperação de uma sessão informa seu ID à
consulta, em vez de filtrar páginas de todas as sessões em Python.

Continuam preservados escopo server/executor/agente, verificação do owner,
paginação por rowid e disponibilidade do histórico para auditoria explícita.
Não houve alteração no protocolo de eventos, externalização de artefatos,
ordenação dos ACKs ou nas provas necessárias para liberar recursos.

A validação cobre históricos sintéticos de 1 mil, 10 mil e 100 mil sessões,
quantidade constante de pendências, instruções da VM SQLite, paginação de mais
de duas páginas, commit/rollback e atualização de banco populado. Os custos
permaneceram constantes nas três escalas; os valores e hashes estão
em `m4b-results.json`. A campanha instalada inclui dispatch, fechamento,
rejeição de lease, perda de ACK, ingresso de eventos e artefatos grandes.
Os cinco primeiros testes source passaram antes de acrescentar o teste de
upgrade e a medição do seletor de agentes; a campanha instalada cobre a versão final.

Limites: a criação inicial dos índices é uma migração atômica; não é backfill
retomável em lotes. M4 ainda precisa dos checkpoints terminais, auditoria
retomável dos journals e orçamento/justiça entre streams. O boot e a recuperação
completa ainda podem percorrer histórico. A instalação global não foi alterada
neste checkpoint. A observação da UI confirmou Live, três agentes locais online
e Pi 4/5 disponível na instalação M3c; isso não qualifica M4b na UI.
