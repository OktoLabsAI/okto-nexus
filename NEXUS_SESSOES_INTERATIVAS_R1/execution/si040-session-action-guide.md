# SI-040 choose a session action from the terminal

The [terminal guide](../../docs/terminal-work.md#choose-a-session-action)
now describes the operator prompt, native user input, queue acceptance and
reviewed steer. It gives separate instructions for live attach, native
saved resume, receipt recovery, new work, interrupt and close. It identifies
the server feature default and the authority required for a local saved
resume. Per-harness viewer instructions retain their specific detach keys
and qualified platform scope.

The installed Nexus 0.3.8 command launcher exposed the documented list and
resume flags. A separate check against the installed configuration parser
confirmed that session interaction defaults to off and that the documented
environment variable enables it. The installed terminal connect and session
CLI suites passed all 69 tests, including exact-session selection and
recovery of the same receipt after an uncertain submission. These checks
used existing test fixtures for receipts and terminal review.

The tests do not supply the outstanding harness and platform qualification
or user acceptance needed by SI-040. This increment edits only the guide
and evidence. It can be reverted without a database, queue or service change.

## Comandos com escopo explícito

O guia passou a exibir o workspace nos exemplos de conexão de Pi e Claude e documenta `session send` para enfileirar uma mensagem com confirmação no terminal. A recuperação usa `session receipt` com a sessão, a geração e o intent do pedido original. No CLI instalado, a seleção remota que omite o workspace retorna `PROJECT_SELECTION_REQUIRED` antes de consultar vínculos.

Os parsers do Nexus 0.3.8 e do Connector 0.0.15 aceitaram 42 exemplos do Nexus e um do Connector. A checagem substituiu os placeholders por valores sintéticos e parou antes da resolução do serviço. A suíte instalada de sessão teve 91 testes aprovados e um ignorado por exigir pseudoterminal POSIX. O marco atualiza o guia e suas evidências, dispensa migração e pode ser revertido pelo commit. O aceite do participante e as campanhas reais continuam pendentes. [Guia](../../docs/terminal-work.md#control-the-session-queue) [Dados e hashes](si040-session-action-guide.json)

A rodada que reuniu as suítes instaladas de `session`, `work` e `connect` no Windows aprovou 214 testes. O único caso ignorado exige pseudoterminal POSIX. A rodada usou o wheel de referência anterior à correção dos seletores de `work resume`. [Resultados e hashes](si040-session-action-guide.json)
