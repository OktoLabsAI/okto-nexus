# SI-T-D09 — Recusa pela API de comandos

A regressão de admissão usa um catálogo vigente, revisão da capacidade
de envio e confirmação explícita. A API recusa `send` com um argumento
iniciado por `!` e recusa um método nativo apresentado como comando
Nexus. Ambas as respostas são HTTP 422. O texto recusado fica fora da
resposta e o adaptador de teste recebe zero envios. O envio válido que
vem depois continua produzindo um único recibo.

Passaram dois testes da API com os wheels instalados, 20 testes Node e
o Ruff. No ensaio separado com Pi real e provedor simulado, a API
também recusou o nome de shell, o método nativo, o argumento de envio
iniciado por `!` e argumentos extras em `status`. O script de
navegador excedeu o tempo de espera pelo login antes de confirmar o
comportamento da Home. O ledger conserva `NOT_RUN` para o cenário
completo. [Relatórios e hashes](si016-shell-api-regressions.json)

O marco adiciona uma regressão e atualiza a evidência. Reverter o
commit remove essa cobertura, sem migração.
