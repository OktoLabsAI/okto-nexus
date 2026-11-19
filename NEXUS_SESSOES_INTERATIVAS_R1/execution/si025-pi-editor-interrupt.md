# Interrupção no editor anexado do Pi

Ctrl+X abre a revisão da execução ativa. Ctrl+Y confirma e grava a pausa da fila na operação canônica. Ctrl+N cancela a revisão. O mesmo terminal mostra quando o Pi confirma a interrupção e conserva o rascunho durante todo o fluxo. A fila volta a despachar após uma retomada explícita.

No ensaio com Pi 0.87.1 real em Windows ConPTY, cancelar manteve a execução e a fila ativas. Uma mudança na revisão da fila invalidou a próxima confirmação. A confirmação válida interrompeu a execução selecionada e preservou o rascunho e a continuação já enfileirada. Desanexar conservou a pausa. O operador recuperou o mesmo recibo por `session receipt`, e a retomada enviou a continuação ao Pi original. O Pi recusou a referência da execução anterior enquanto a continuação rodava. O ensaio usou respostas simuladas. [Dados do ensaio](si025-pi-editor-interrupt.json)

Os testes de transporte verificaram que um token de revisão de interrupção não autoriza reorientação e que trocar o terminal escritor invalida a revisão anterior. A recuperação usa a intenção originada no terminal e a autoridade do mesmo login. O ensaio pode ser reproduzido com `si025-pi-terminal-e2e.py --interrupt --interrupt-surface editor`.

Passaram 80 testes do Nexus instalado e o ensaio de reorientação no editor. A coleta do teste agora espera a última mensagem mesmo quando o processo já terminou. A etapa dispensa migração. Para reverter, use `git revert` no commit do Nexus desta etapa.

A SI-025 continua em andamento. Aprovações, teste no navegador e qualificação com provedor real continuam pendentes.
