# ADR HOME-R1 — visualização de resultados

Estado: aceito para implementação; validação pendente nos cenários C08/D05/D06.

1. Reutilizar o episódio canônico `result_unseen` e sua preferência por
   attention_id/source_revision/preference_revision. Não criar tabela ou
   watermark de resultados da Home.
2. Visto é ação explícita após abrir, pela API/CAS existente. Abrir Home,
   mostrar preview, filtrar ou paginar não escreve visto, ACK ou decisão.
3. Resultados sem episódio rastreável usam `view_state=not_tracked` e rótulo
   Recentes. O contador de novos fica null/indisponível quando não for exato.
4. Preference pertence ao operador e episódio; visto/adiado não modifica o
   resultado, estado de execução, handoff ou entrega de inbox.
5. Novo episódio/revisão é uma identidade de atenção distinta; fonte removida,
   autorização perdida ou conflito não autoriza marcar outro item.

Consequência: a Home compõe leitura e preferência compartilhadas, sem aumentar
o poder do observador. Qualquer futura unificação de rastreamento de todos os
resultados exige outra decisão explícita; não integra o MVP por inferência.
