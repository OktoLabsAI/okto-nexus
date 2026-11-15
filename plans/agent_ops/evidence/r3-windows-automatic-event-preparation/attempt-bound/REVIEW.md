# Sucessor Windows com tentativa vinculada — UNSELECTED

Corrige a lacuna encontrada no suplemento anterior: um logon independente não pode consumir `after.reserved` ou ser associado ao evento planejado sem uma tentativa selecionada. O diretório predecessor e seus hashes permanecem intactos; `ancestry.json` os registra.

`collect.after` agora exige `event-attempt.json` vinculando SHA do plano e do before, evento, principal próprio, janela exata e comando derivado. O horário da tentativa precisa estar dentro da janela e depois do before. Ausência de tentativa ou recusa positiva antes do comando retorna **sem reservar after**. Pins inválidos recusam. O after válido publica também o pin da tentativa. Nenhum `performed_by_user=True` é fabricado.

`execute_event.py` é o executor concreto, separado do seletor. Ele só funciona com plano selecionado e `--execute-selected-event`. Antes de agir, lê o before pinado, reabre os seis handles atuais, exige ambos READY, compara PID/birth/coorte/geração/task digest e o mesmo principal/logon. Revalida a janela e cria a tentativa exclusivamente, com fsync/publicação atômica. Antes do comando, verifica novamente janela e handles. Se essa última verificação falhar, a tentativa continua consumida e um recibo `REFUSED_BEFORE_OS_CALL` impede a coleta after correspondente. Resultado desconhecido nunca é repetido.

Comandos derivados continuam exatamente `/l`, `/r /t 0`, ou `SetSuspendState(FALSE,FALSE,FALSE)`. Não há `/f`, timeout positivo de shutdown, autologin, senha, elevação, start/stop de serviços ou próximo evento automático. Suspensão habilita somente SeShutdownPrivilege já atribuído ao token próprio; ausência recusa, sem fallback. O argumento Force de SetSuspendState é obsoleto, não uma garantia de encerramento gracioso. Nenhum código0/retorno da API prova o evento: `event_proven` no recibo de comando é sempre false; os fatos posteriores de boot/logon e history são separados, e suspensão ainda exige prova independente.

## Sequência futura

1. Root e usuário selecionam a janela concreta depois de M1. Preparar os serviços no fluxo separado e comprovar READY atual; não reutilizar histórico como liveness.
2. Usar **este** `select_event.py` com SHA de **este** plan-template, um evento e janela UTC de até30min. Ele só cria arquivos/XML; não publica tarefa nem executa evento. Pasta por evento exclusiva.
3. Registrar/revisar a tarefa observadora própria, sem colisão/Force/senha, InteractiveToken/LeastPrivilege do próprio SID. É responsabilidade explícita do root verificar a definição real/ação/pins antes do evento; registro e cleanup não são executados por este suplemento. A tarefa executa somente o after RO.
4. Executar `commands.json.before` e manter seu observer. Depois executar **somente `commands.json.execute_once`** (prefixar com `rtk proxy`). Não executar `derived_command_for_review_only` diretamente, pois isso contornaria a reserva. Argv efetivo:

   `<Q/python.exe> -I -B -X utf8 <this/execute_event.py> --plan <selected-plan.json> --sha256 <selected-SHA> --execute-selected-event`

5. Login após logout/reboot continua manual. A tarefa coleta after; pós-suspensão o root chama after quando retornar. Wake automático continua não selecionado neste Modern Standby. Se nenhuma tentativa válida existir, um login alheio ao teste não consome a coleta.
6. Revisar history e fatos reais, sem inferir saída física se o observer de handles morreu no logoff/reboot. Cleanup somente da tarefa observadora exata, após terminar, conferindo definição/principal/ação; nunca encerrar observer para limpar nem alterar as duas tarefas dos serviços.

Os guardas de seis handles não eliminam a corrida inevitável entre a última leitura e a chamada de SO; o executor mantém os handles e registra o resultado como tentativa, sem promessa de atomicidade ou continuidade. Se o processo morrer após reservar e antes de chamar o SO, a tentativa fica incerta/consumida; não se reconstrói um sucesso nem se repete automaticamente.

Qualificação offline: **6 testes PASS**, com snapshots, handles e dispatch injetados. Cobrem logon sem tentativa, pins/principal/janela divergentes, expiração/owner alterado, tentativa legítima e after correlacionado, replay, expiração após reserva e retorno incerto. Não houve chamada SetSuspendState/shutdown, publicação de tarefa, lifecycle, provedor ou login. As referências Microsoft e limitações de Modern Standby do REVIEW predecessor continuam aplicáveis. Nenhuma janela ou seleção foi criada aqui.
