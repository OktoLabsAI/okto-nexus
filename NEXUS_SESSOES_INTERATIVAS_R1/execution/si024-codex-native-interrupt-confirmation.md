# Interromper o turno pelo visualizador do Codex

No Windows, abra a sessão com `session attach --write`. Durante um turno ativo, **Esc** abre a confirmação para aquele turno. O console mostra o identificador do turno e explica que a fila será pausada. **Ctrl+Y** confirma, **Ctrl+N** cancela e **Ctrl+]** fecha o visualizador. A revisão local expira em 30 segundos.

O Nexus revalida o escritor, a thread, o turno, a capacidade e a revisão da fila antes de admitir a interrupção. Ele registra a pausa da fila na mesma transação que admite o controle. O console diferencia cancelamento, revisão recusada, interrupção registrada e interrupção confirmada. A confirmação depende do recibo canônico do turno. Se a confirmação ficar indisponível, o console informa que o resultado é incerto e indica a sessão para consulta.

A sessão permanece disponível após a interrupção. A retomada da fila exige uma ação separada. O Nexus mantém os itens pendentes e a concessão da sessão.

O ensaio automatizado usou Codex 0.170.0 em Windows ConPTY, app-server real 0.157.0 e respostas determinísticas em loopback. Cancelar deixou a fila disponível e o turno ativo. Uma revisão antiga foi recusada após o início do turno seguinte. A confirmação válida gerou uma chamada nativa, depois que a pausa foi gravada. Desanexar preservou o processo e a entrada enfileirada. A retomada explícita enviou a entrada para a mesma thread. [Dados dos ensaios](si024-codex-native-interrupt-confirmation.json)

A regressão com o mesmo wheel confirmou que a ação de reorientar continua produzindo uma única reorientação. Um teste no WebSocket cobre a recusa ao confirmar uma ação com o identificador da revisão de outra. As 42 regressões passaram no código-fonte e no wheel. O Twine validou os pacotes e o Ruff aprovou os arquivos alterados. A checagem global do Ruff ainda acusa problemas em arquivos fora desta etapa.

A alteração dispensa migração. Reverter o commit remove a confirmação por Esc e preserva os recibos, a fila e os controles existentes da Home e do CLI.

A qualificação segue com a perda de capacidade durante a sessão e a compatibilidade com versões anteriores. Os ensaios desta etapa cobrem a apresentação local.
