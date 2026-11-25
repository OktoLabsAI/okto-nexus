# SI-021 · Escopo e autoridade na apresentação nativa

O app-server Codex 0.157.0 abriu duas threads descartáveis em um único processo. O terminal Codex 0.170.0 apresentou a thread selecionada por WSS em loopback. O relay recusou a listagem geral e os pedidos de leitura, retomada e histórico da outra thread. O Server encerrou a tentativa de leitura fora do escopo. As duas threads continuaram legíveis pelo proprietário depois da saída do terminal.

A auditoria registrou três anexações de leitura desanexadas ao final, com os hashes de tickets descartados e zero operações de trabalho, entradas de fila ou controles novos. O processo do app-server e o listener de teste encerraram. [Auditoria nativa e hashes](si021-current-native-authority.json)

No wheel instalado, passaram o ensaio nativo e 104 regressões de permissões, contratos de apresentação e transporte. As regressões exercitaram revogação, recuperação da operação já autorizada e disputa pelo último uso disponível de um grant. A evidência de disputa por um mesmo turno entre agente e humano está no ensaio do árbitro compartilhado. [Árbitro compartilhado](si007-shared-turn-arbitration.json)

As campanhas SI-T-G09 e SI-T-G10 continuam pendentes.
