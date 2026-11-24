# SI-034 · Recibos de decisões no terminal

`work answer`, `work status` e `work watch` conferem o ID da decisão, a chave da aprovação e o hash do pedido antes de exibir o recibo recuperado. Quando o runtime recusa uma decisão antes do efeito, o CLI confere o vínculo, a sessão, a geração do dono e a ação da operação que explica a recusa. O CLI recupera o recibo por leitura e preserva o checkpoint.

O ensaio substitui os campos em respostas locais. As sete variações exercitam ID e hash divergentes, outra sessão, outra geração, outro vínculo e outra ação. As regressões de API e SQLite também conferem recuperação após perda de resposta, decisão concorrente pelo dashboard e leitura durante parada controlada. A mudança dispensa migração e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si034-terminal-decision-receipts.json)

As sete variações falharam no wheel anterior. Passaram 12 casos no código-fonte e os mesmos 12 no wheel corrigido, com peers sintéticos.
