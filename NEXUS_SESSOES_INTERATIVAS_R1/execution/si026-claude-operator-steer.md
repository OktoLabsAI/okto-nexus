# Reorientação de um turno Claude pelo painel

Na conversa da sessão gerenciada pela Home, **Reorient current turn** abre a revisão do rascunho ou da mensagem da fila. A confirmação **Interrupt and send** descreve o efeito antes da ação. O Core só escreve a nova mensagem depois de confirmar a interrupção do turno revisado.

O Nexus conserva a referência da operação original e o stream observado. A revisão fica indisponível antes do início da geração e enquanto permanece um resultado incerto daquela reorientação. Cada confirmação e consulta pertence à sessão e ao operador originais. Após uma perda de resposta, o painel consulta o mesmo recibo e mantém a possibilidade de efeito até receber evidência suficiente.

O recibo distingue a interrupção e o envio. Uma confirmação tardia do resultado da nova mensagem resolve uma escrita incerta pelo mesmo recibo. No Edge, cancelar a revisão preservou o rascunho e produziu zero controles. O ensaio descartou a resposta HTTP de confirmação, consultou o recibo, recarregou a Home e publicou um resultado tardio da mesma operação. Houve uma única chamada ao adaptador simulado.

A migração 184 cria a tabela que vincula a confirmação ao alvo e ao stream. O rollback reverte o commit e restaura o painel e o backend anteriores. Preserve a tabela aditiva e reconcilie operações pendentes antes de testar o rollback. O pin do Core continua na revisão já testada com o subprocesso de protocolo simulado.

SI-026 continua em andamento. Os ensaios deste marco usaram a Home compilada, HTTP real, Core instalado e eventos sintéticos. A próxima validação de SI-026 precisa cobrir o terminal nativo Claude, a continuidade da sessão com sua configuração e o transporte remoto. [Dados dos ensaios](si026-claude-operator-steer.json)
