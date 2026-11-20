# SI-T-D09 — Rascunhos com prefixo de shell na Home

O teste usou Edge e Pi 0.87.1 no Windows, com os wheels instalados, R4
em loopback e um provedor simulado. A Home abriu a conversa da sessão
ativa. Pressionar Enter preservou tanto o rascunho iniciado por `!`
quanto o mesmo texto como argumento de `/send`. O navegador registrou
zero requisições de execução nessas tentativas. A ação autorizada
`/status` respondeu HTTP 200. [Resultados e hashes](si016-browser-shell-boundary.json)

A API respondeu HTTP 422 aos quatro pedidos de teste. Eles cobriram o
nome de shell, um método nativo fora do catálogo, um argumento de
`send` iniciado por `!` e argumentos extras em `status`.

A auditoria em modo somente leitura confirmou uma abertura, um turno e
um fechamento na mesma sessão, com um resultado e zero entradas na
fila. A verificação de integridade e de chaves estrangeiras do SQLite
passou. O navegador e o processo nativo temporários encerraram.

O ensaio integrado passou após duas tentativas interrompidas na
preparação. A primeira não chegou ao editor a partir do formulário de
login. A segunda excedeu o prazo de inicialização HTTP da fixture.
O ensaio aprovado usou a rota oficial de login, abriu o Edge antes de
esperar a sessão e ampliou o prazo de inicialização da fixture. Os dois
testes de API e 20 testes Node do marco anterior também passaram no
mesmo build. [Regressão da API](si016-shell-api-regressions.md)

O marco atualiza a evidência e o ledger do cenário no Windows.
Reverter o commit remove esse registro, sem migração.
