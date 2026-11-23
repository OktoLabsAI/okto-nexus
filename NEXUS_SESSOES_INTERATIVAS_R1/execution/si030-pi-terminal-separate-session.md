# SI-030 · Abrir uma sessão separada pelo editor do Pi

No Windows, Ctrl+O no editor de `okto-nexus session attach --write` abre a revisão do Nexus para uma sessão vazia. Ctrl+N cancela e mantém o editor original. Ctrl+Y confirma a abertura canônica e devolve o comando para anexar ao ID exato confirmado pelo servidor. A sessão de origem mantém sua fila e tem seu próprio comando para retornar. A revisão aguarda enquanto houver rascunho ou controle pendente.

O visualizador fecha após a confirmação. O CLI usa a autorização da conexão, grava o checkpoint antes da admissão e valida o recibo. Quando há um checkpoint anterior sem admissão registrada, o CLI orienta a revisão pelo comando `session open`. Se o recibo demora mais que a janela de observação, a recuperação consulta a operação existente.

Um ensaio expôs perda de resposta na transição de modo do ConPTY. A confirmação passou para dentro do editor. Outro ensaio isolou a perda da primeira tecla ao reabrir a entrada no mesmo processo. A abertura agora volta ao shell com o comando exato, e a anexação começa em um processo separado. O CLI informa Ctrl+] para desanexar o editor.

No pacote instalado, o ensaio com Pi 0.87.1 manteve o primeiro turno em andamento enquanto uma entrada aguardava na fila. O roteiro verificou o rascunho, o cancelamento, a segunda abertura, o comando de anexação e o detach nas duas sessões. A sessão vazia abriu sem invocar o modelo. A entrada pendente foi executada uma vez pelo Pi de origem. O fechamento canônico encerrou os dois processos.

Passaram 60 testes de CLI no código-fonte, 63 regressões de CLI e do Connector com o pacote instalado e um ensaio nativo no Windows. O ensaio nativo usou um modelo simulado. Os três casos do Connector usaram um renderer de teste. A qualificação remota nativa e a campanha por harness e plataforma permanecem abertas em SI-T-G20. [Resultados e hashes](si030-pi-terminal-separate-session.json)

A alteração dispensa migração. Para voltar ao wheel anterior, resolva primeiro qualquer checkpoint de abertura pendente com o comando atual.
