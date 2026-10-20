# M5w: reset com Connector local e Pi real pela UI instalada

Fixture descartável: Nexus 0.3.1/Core 0.0.12 em `127.0.0.1:8204`, Connector
0.0.10/Core 0.0.12 em processo separado na mesma máquina, Pi 0.87.1 nos
caminhos embedded e Connector. O host remoto físico não integra este teste.

O agente `m5w-pi-remote` foi cadastrado em Agents, conectado pelo assistente
do Connector ao workspace M5V e autorizado na página Approvals. Agents mostrou
`Remote · Online`; o Connector informou `CONNECTED`/`CONTROL_READY`. A mensagem
de referência `M5W_REMOTE_CONNECTED_OK` retornou exatamente o marcador, com
ACK 1/1. O agente embedded `m5v-pi` já tinha resposta exata anterior.

Antes do reset: 3 agentes, 1 workspace, 2 bindings, 2 sessões, 8 mensagens e
8 entregas, 10 eventos. Em Settings > Storage, com **Preserve agents, API keys
and connection settings** marcado, a primeira tentativa recusou com
`Representing another agent requires an authenticated operator.` A UI tinha
autenticado o operador, mas o encerramento das sessões remotas passava seu
contexto sem `actor_agent_id=operator`. Nada foi apagado. Corrigimos a
atribuição apenas para o operador já autenticado pelo dashboard; o teste
direcionado de autorização passou.

Na repetição pela UI, o reset terminou `pending=false`, `kept_agents=true`.
O retorno informou 2 `execution_sessions`, 8 mensagens, 8 entregas e 10
eventos removidos. Conferência direta confirmou 3 agentes, 1 workspace, 2
bindings preservados e zero sessões/mensagens/entregas/eventos. Agents mostrou
os dois Pi Online, sem recriar conexão. O Connector permaneceu `CONTROL_READY`.
A mensagem posterior ao Connector teve ACK 1/1 e resposta exata
`M5W_REMOTE_AFTER_RESET_OK`. Isso aprova o critério de reset remoto em loopback.

A autorização de 60 minutos do Pi embedded, criada antes deste teste, havia
expirado às 09:21 UTC. A primeira chamada local pós-reset falhou
`PERMISSION_DENIED` por essa expiração, independente do reset. Ela deixou
sessões `FAILED/NONE` com prova de liberação. A API e a modal de Connections
as tratavam como ativas e ofereciam Close, que respondia `session_not_ready`.
Alinhamos os filtros de sessão liberada no Server e na UI. O teste de
regressão distingue `FAILED/ACTIVE` (ainda bloqueia substituição) de
`FAILED/NONE` e `FAILED/CLOSED` (não bloqueiam). Pela UI, alteramos a duração
da autorização para Unlimited, executamos o teste real de conexão, salvamos,
e repetimos a chamada. `M5W_LOCAL_REAUTHORIZED_OK` retornou exatamente, com
ACK 1/1. Build do dashboard e testes direcionados passaram.

**Falha ainda aberta no critério M8 de recuperação após restart:** para
instalar os ajustes durante este fixture, o Server foi encerrado à força e
reiniciado várias vezes. Após essas reinicializações adicionais, o Connector
passou a `RECOVERY_ATTENTION_REQUIRED`/`CONTROL_DISCONNECTED` e repetiu
fechamentos WebSocket `4406`; Agents passou a mostrar o agente remoto Offline.
Um reinício controlado somente do daemon do Connector não resolveu. Um cliente
de diagnóstico usando a mesma instalação Core, URL, identidade de servidor e
executor existente recebeu `welcome` R4, então a incompatibilidade está no
caminho de reconexão do daemon ou em seu estado persistido, ainda sem causa
comprovada. Este achado não invalida a entrega real feita imediatamente após
o reset; impede afirmar recuperação automática para a sequência de restarts.
Não houve correção de protocolo nem aprovação do M8 neste checkpoint.
