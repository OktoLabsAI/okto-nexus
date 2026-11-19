# Confirmar a reorientação no terminal do Codex

Ao abrir uma sessão com `session attach --write` no Windows, Enter durante um turno ativo mostra o turno que receberá a reorientação e uma prévia do texto. **Ctrl+Y** confirma, **Ctrl+N** cancela e **Ctrl+]** encerra apenas o visualizador. A confirmação local expira em 30 segundos. Se a fila ou o turno mudarem durante a revisão, o Nexus recusa a confirmação. Para enviar uma mensagem em outro turno, o operador pode enfileirá-la pela Home ou usar `session send`.

O terminal usa a mesma revisão de turno da Home. O servidor associa a revisão à conexão WebSocket e revalida o escritor, a thread, o turno, a capacidade e a revisão da fila antes de gravar a entrada. A aprovação vale para uma confirmação. O relay recusa reutilizar a mesma mensagem como um novo turno após a tentativa de reorientação.

O ensaio usou o frontend Codex 0.170.0 e o app-server 0.157.0 em Windows ConPTY, com respostas determinísticas em loopback. A sessão permaneceu na mesma thread. Cancelar preservou o turno e, depois que ele terminou, o texto continuou sem envio. Uma entrada enfileirada pela Home invalidou uma segunda revisão. A terceira revisão produziu uma única chamada nativa de reorientação, no segundo turno da mesma thread. O par local observou somente o texto aprovado entre as tentativas de reorientação. [Dados dos ensaios](si024-codex-native-steer-confirmation.json)

O recibo da reorientação continuou em `DISPATCHING` nesse ensaio. O Nexus mostra a confirmação nativa como pendente e o operador pode sair com **Ctrl+]**. A observação pelo par de teste comprova o texto e o turno recebidos nesse ambiente. A comprovação durável de consumo, a confirmação de interrupção pelo próprio visualizador e a qualificação remota seguem em aberto.

A alteração dispensa migração. Reverter o commit restaura a orientação para reorientar pela Home ou pelo CLI e preserva os recibos gravados. A próxima etapa é a confirmação de interrupção no visualizador.
