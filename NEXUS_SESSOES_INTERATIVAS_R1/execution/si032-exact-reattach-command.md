# SI-029 e SI-032 — Comando para reanexar após sair do terminal

Ao desanexar de uma apresentação nativa pelo CLI, o Nexus imprime **Reattach to this session** com um comando para o vínculo, revisão, host, workspace e sessão confirmados. O comando usa o mesmo perfil de operador e a mesma pasta de dados do cliente. O modo de escrita e o caminho do visualizador são preservados quando fornecidos na chamada. Valores são tratados como argumentos de shell, e o comando omite credenciais e tickets de apresentação. O CLI valida novamente o vínculo e a sessão quando o comando é usado.

O caminho de `connect -i` usa a mesma saída após um detach bem-sucedido. A configuração continua confirmada se o visualizador recusar a abertura. A regressão verificou o recibo de configuração, a saída do CLI, a recusa de servidor, host ou revisão divergente e o resultado separado do handoff. [Teste do CLI](../../tests/session_interaction/test_session_cli.py) · [Teste de `connect`](../../tests/execution_r4/test_terminal_connect.py)

Passaram 247 testes em código-fonte e 247 no wheel instalado, incluindo compatibilidade de Quick Connect, `work resume`, perfis, participante e handoffs. O wheel anterior reproduziu a ausência do comando depois de um detach bem-sucedido.

Com Pi 0.87.1 real no Windows, o teste extraiu os argumentos do comando em sintaxe PowerShell e os passou novamente ao CLI instalado, em outro terminal ConPTY. O segundo terminal mostrou o resultado da mesma sessão. O PID, o vínculo e a operação permaneceram os mesmos, e o histórico nativo reteve uma única mensagem do usuário. Uma checagem separada executou o comando no PowerShell 7.6.10 com uma função de captura e conferiu os dez argumentos. O provedor foi simulado e a autenticação usou um perfil temporário com cofre de teste. [Artefatos do ensaio](si032-exact-reattach-command.json)

Em um segundo ensaio, a API v2 da Home trouxe o mesmo card em Active antes e após o detach, com a conexão `connected` e a atividade `working` enquanto o turno ainda rodava. Os 29 testes de contratos da Home em Node também verificaram identificação de contexto, estados e comando copiado no painel. A observação dessa etapa usou a API e o CLI. A validação em navegador, a aceitação humana e a qualificação em outros sistemas seguem abertas.

A orientação de `connect` no guia agora descreve a oferta do visualizador nativo com padrão Não. A mudança é no CLI e na documentação, e o commit pode ser revertido sem migração. [Guia do terminal](../../docs/terminal-work.md)
