# SI-034 · Recibos de decisões no terminal

`work answer`, `work status` e `work watch` conferem o ID da decisão, a chave da aprovação e o hash do pedido antes de exibir o recibo recuperado. Quando o runtime recusa uma decisão antes do efeito, o CLI confere o vínculo, a sessão, a geração do dono e a ação da operação que explica a recusa. O CLI recupera o recibo por leitura e preserva o checkpoint.

O ensaio substitui os campos em respostas locais. As sete variações exercitam ID e hash divergentes, outra sessão, outra geração, outro vínculo e outra ação. As regressões de API e SQLite também conferem recuperação após perda de resposta, decisão concorrente pelo dashboard e leitura durante parada controlada. A mudança dispensa migração e pode ser revertida pelo commit do Nexus. [Comandos e resultados](si034-terminal-decision-receipts.json)

As sete variações falharam no wheel anterior. Passaram 12 casos no código-fonte e os mesmos 12 no wheel corrigido, com peers sintéticos.

## Checkpoints de respostas pendentes

O CLI conserva as tentativas incertas por ID da pergunta. Cada entrada guarda a intenção e o hash da resposta. Tratar uma segunda pergunta preserva a primeira tentativa, inclusive depois de reabrir o perfil. Uma confirmação ou recusa de validação limpa apenas a entrada correspondente.

O formato 1 continua legível. Na primeira gravação de um checkpoint antigo, o CLI preserva a decisão anterior para recuperação. O commit pode ser revertido sem migração. Antes de voltar a um wheel que só lê a última decisão, use o pacote atual para reconciliar os recibos ainda pendentes. [Comandos e resultados](si034-terminal-decision-receipts.json)

Os seis cenários falharam no wheel anterior. Passaram 17 testes no código-fonte e os mesmos 17 no wheel corrigido. A execução também verificou a limpeza da entrada após recuperar o recibo canônico e a preservação do hash sem o texto da resposta.
