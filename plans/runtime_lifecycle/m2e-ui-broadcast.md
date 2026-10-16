# M2e — Validação real no Meta-harness

Data: 2026-10-16, Windows nativo, instalação global dos três pacotes e hashes
descritos em `m2e-validation.md`. Core `90b4ef6`, Connector `2dca512`; o commit
Nexus pode ser localizado pela adição deste relatório. Servidor em
`http://127.0.0.1:8202`, executor embedded geração 66.

## Roteiro e resultado observado

Pela interface, foi enviado um broadcast no workspace Techridy às 18:51:04 UTC,
com assunto `Runtime M2e · recuperação compartilhada · 20261016`. A instrução
pedia somente `NEXUS_M2E_UI_20261016_OK`, sem ferramentas, arquivos ou tarefas.

| Harness | Sessão | Resultado na interface |
|---|---|---|
| Claude | `ses_48506953578b1b11253310e3f8c9085c` | Marcador exato; sessão persistente aberta |
| Pi | `ses_377dc611465a4203149419669c41b39d` | Marcador exato; sessão one-shot encerrada |
| Codex | `ses_67681c4e2051da54dbc6ddca5bc4f38c` | Falha entregue ao chamador; terminal confirmou `usageLimitExceeded` |

O Meta-harness mostrou um cartão de broadcast e três ACKs. No terminal do
Codex, o harness e o MCP Nexus ficaram prontos antes da tentativa; o provedor
recusou a execução por limite de uso. Não foram repetidas chamadas, alteradas
contas, modelos ou credenciais para contornar essa restrição. Portanto, esta
campanha **não comprova resposta bem-sucedida dos três provedores**.

Após o teste, Agents mostrou Pi, Claude e Codex como Local · Online, sem ação
de Retry recovery. O pool Pi mostrou 4/5 disponíveis. A conexão remota revogada
existente não foi alterada. Não houve reload da página para obter a recuperação.

## Achados e limites

- O servidor iniciou às 18:47:51 UTC e só disponibilizou HTTP por volta de
  18:50 UTC. O stack dump local mostrou `EmbeddedInventoryOwner.start`
  aguardando descoberta/identidade do Pi. M3b vai separar esse trabalho da
  prontidão HTTP; não se trata de atraso do provedor no atendimento do broadcast.
- Os tooltips de Agents ainda mostram `Last contact: never` junto de Ready;
  a semântica de presença faz parte de M3.
- O texto visível dos ACKs mostrou 3/3, enquanto o aria-label ainda indicava
  0/3. Registrado para correção da projeção acessível.
- O terminal também mostrou falhas de MCPs globais do Codex, distintas da
  quota. A saída bruta contém configuração sensível e não foi incluída neste
  relatório nem em screenshots commitadas.
- Logs, snapshot anterior do banco, verificação da instalação e stack dump
  permanecem em `build/runtime-lifecycle-m2e-live/`, ignorado pelo Git.

Este é um teste real intermediário pela UI. Não conclui o gate UI-A, os testes
de pressão, as demais fronteiras de crash ou a qualificação de outro host.
