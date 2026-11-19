# SI-026 Interrupção e reenvio no Claude stream-json

O Core consulta a autorização antes de cada escrita no processo. Se a interrupção já pode ter ocorrido e a segunda escrita é recusada, o recibo da operação composta registra `OUTCOME_UNKNOWN` com efeito possível e sem repetição automática. A ponte remove a correlação da substituição quando prova que ela ficou sem envio. O resultado do turno original continua vinculado à operação original.

Os eventos registram a operação original, a operação de reorientação e o identificador do pedido de interrupção. Distinguem escrita concluída, escrita de resultado incerto e substituição recusada antes da escrita. O teste confirmou o identificador da resposta do processo e os resultados terminais em separado.

O ensaio usou um subprocesso Python com o protocolo simulado do Claude e o diário SQLite real do Core. Cobriu cinco casos. A recusa anterior à interrupção manteve o turno original. Perder a confirmação da interrupção ou recusar a substituição depois dela preservou o efeito possível sem enviar outro turno. Perder a confirmação da substituição deixou o recibo incerto até o resultado nativo correspondente. O caso normal registrou o cancelamento do primeiro turno e a conclusão da substituição. Recuperar ou repetir o mesmo identificador em qualquer caso manteve a contagem de escritas.

Passaram 49 testes do Core instalado, oito do Connector e quatro do Nexus com a mesma wheel. O wheel e o sdist passaram no Twine estrito. A mudança dispensa migração e atualização de contrato público. Para reverter, recoloque os pins anteriores do Core no Nexus e no Connector junto com a reversão da alteração no Core.

O teste cobre o transporte simulado e o diário do Core. A tela de confirmação do efeito composto, a concorrência HTTP, o terminal nativo do Claude e a operação remota continuam em qualificação. Houve zero chamadas a provedores. [Dados do ensaio](si026-claude-compound-steer.json)
