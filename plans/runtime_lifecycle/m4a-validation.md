# M4a — Liberação com consulta por sessão

A liberação de uma sessão embedded consultava todos os registros históricos e
só depois selecionava o ID solicitado. Além do custo por fechamento, o limite
de 32.768 registros do plano de recuperação impedia liberar uma sessão em uma
instalação com histórico maior. A consulta agora usa a chave composta exata
server/executor/session. Preserva a verificação do owner, escopo do agente e
rejeição de associação ausente ou ambígua; nenhuma prova de liberação mudou.

Em 2026-10-16, **30 testes da wheel instalada passaram**, sem falhas, erros ou
skips e com `changed_inputs=[]`. Incluem a consulta em bases sintéticas de
1 mil/10 mil/100 mil sessões no schema migrado, recuperação de recursos,
seis fronteiras de crash com processos Windows descartáveis e isolamento de
agentes. A consulta encontrada usou 255 instruções SQLite e a inexistente 201
em todas as três escalas. Não se inferiu desempenho por duração de um teste.

A primeira execução source teve três falhas: o limite arbitrário de 100
instruções para a consulta inexistente era menor que o custo fixo observado
(201 nas três escalas). O teste passou a usar o mesmo teto de 500 instruções
da busca encontrada; a campanha instalada confirmou o limite com inputs fixos.
Os casos de escopo, associação ambígua e identidade exata passaram desde a
primeira execução. Evidências e hashes: `m4a-results.json`.

Este checkpoint não conclui M4: a descoberta global de journals, o backfill/
checkpoint terminal durável, os índices de pendências e a justiça de streams
continuam pendentes. A instalação global permanece M3c; somente o ambiente
isolado recebeu M4a com Core/Connector M3e. A mudança não exige migração de DB.
