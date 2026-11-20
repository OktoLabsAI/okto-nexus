# SI-T-A06 — Mesmo ID de harness em projetos diferentes

A API de setup criou dois workspaces em diretórios distintos com o
mesmo nome público. Os dois usaram o mesmo ID de harness, executor
e agente. A consulta por workspace e ID retornou uma referência
canônica distinta para cada conexão.

Depois de confirmar o workspace, o teste abriu as duas sessões.
Um envio que misturava o ID da sessão escolhida com o workspace
irmão recebeu HTTP 409. O envio com escopo exato retornou HTTP 202
e produziu um turno apenas na sessão escolhida. Os dois controles
de fechamento terminaram com sucesso.
[Relatório e hashes](si006-homonymous-workspace-scope.json)

Passaram o teste no pacote instalado e a auditoria SQLite. A
auditoria encontrou dois IDs públicos iguais em bindings distintos,
uma entrada entregue e um resultado no workspace escolhido.
O teste usa as APIs de setup, consulta e envio com peers de
protocolo simulados. O marco dispensa migração. Reverter o
commit remove o registro.
