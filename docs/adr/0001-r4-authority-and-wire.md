# ADR 0001: Autoridade e representação da integração R4

Status: aceito para implementação em `feature/v0.2.0`.

## Decisão

O pacote `nexus-connector-core` é a única fonte dos schemas NXL, do codec,
do hash de intenções, dos reducers e das capacidades de adapters. A revisão
R3 e seus bytes persistidos permanecem imutáveis. Um efeito novo exige a
revisão R4 exata e o mesmo artefato Core qualificado nos dois hosts.

O Nexus autentica, resolve escopo, admite a intenção uma vez, persiste a
operação e é o único dispatcher de efeitos. O Connector executa operações
admitidas na lane remota e reporta recibos; o Nexus local usa o mesmo Core em
processo, sem depender do aplicativo Connector ou de loopback WSS.

`/v1` responde objetos JSON diretos. Seus erros usam `error` com código,
estágio, `possible_effect`, `retry_safe`, operação e ação. Todas as respostas
levam `X-Nexus-Connections-Revision`; credenciais nessa superfície usam
somente `Authorization: Bearer`. `/api/v1` mantém o envelope `ok/data/error`
para compatibilidade e chama os mesmos casos de uso ao migrar cada rota.
`/mcp` continua HTTP e preserva a extração legada até migração explícita da
entrada escolhida pelo operador. Uma chave em URL nunca aparece em nova
configuração gerada.

O Server cria `AuthenticatedPrincipal` de credenciais verificadas. O contexto
de conexão do executor deriva do ticket e da geração do socket; valores do
corpo são assertions a comparar, não autoridade. Ticket NXL e capability MCP
possuem audiências diferentes. `approval.decision` comunica o resultado;
somente `operation.submit` com `approval.decide` ou `input.provide` aplica o
efeito correspondente.

`runtime.open` remoto leva referências de inventário e realização, nunca
`executable`, `argv`, `env`, path ou PID recebidos da rede. Antes de uma lease
inicial correlacionada e instalada no Core, a lane pode apenas resolver a
realização e pedir a lease. `binding.attached`, `reconcile.accepted` e
`lease.applied` são confirmações separadas. Socket aberto, envio bem-sucedido
e resposta HTTP positiva não equivalem a prontidão nem a efeito aplicado.

## Estado de implementação

Este ADR fixa o alvo descrito em `plans/02_CONTRATOS_HTTP_NXL_E_ESTADOS.md`.
O endpoint `/v1/connections/protocol` já segue a representação direta e
anuncia `remote_execution_ready=false` enquanto o bundle R4 não está pronto.
As demais rotas e o dispatcher ainda exigem implementação e evidência dos
gates G0–G3. Nenhum cliente deve promover capacidade a partir deste ADR.
