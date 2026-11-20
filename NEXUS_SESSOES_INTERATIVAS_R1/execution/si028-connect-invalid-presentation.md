# SI-T-F06, SI-T-F08 e SI-T-F10 — Recusas no CLI instalado

O executável instalado foi chamado com um perfil e um projeto descartáveis.
Com stdin e stdout redirecionados, `connect -i` retornou código 2 e pediu
entrada e saída de terminal. Um teste complementar isolou o caso em que só
a saída deixa de ser um terminal e verificou que a resolução do serviço
não foi chamada.

No Windows ConPTY, a combinação de `-i` com `--no-interactive` ou
`--no-chat` retornou código 2 nas duas ordens. `-ni` indicou a opção
`--no-interactive`, e `--inter` foi identificado como argumento
desconhecido. Em cada uma das sete invocações, o diretório do Nexus
continuou ausente, o inventário do projeto e do perfil ficou idêntico
e o socket de teste não recebeu conexões.
[Resultados por invocação e hashes](si028-connect-invalid-presentation.json)

Passaram sete testes com o wheel instalado, incluindo o ensaio do
executável, cinco casos do parser e o caso de saída redirecionada.
O marco atualiza as evidências e o ledger. Reverter o commit remove esse
registro e dispensa migração.
