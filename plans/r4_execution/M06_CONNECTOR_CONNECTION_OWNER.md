# M06 — leitor único R4 no Connector

Status: **integração técnica parcial**, sem fechamento de gate.

O Connector agora oferece `connect_r4_connection` e `R4Connection`: negociação
do canal seguida de um único reader, respostas de lease/attach correlacionadas
por ID, writer serializado e inboxes limitadas para operações produtivas e de
controle. Cada reserva mantém os bytes originais e seu custo até o produtor
concluir. Rotação e desconexão invalidam a autoridade; um ACK antigo não
restaura a lane. A chamada ao Core continua exigindo revalidação após esperas.

O owner preserva o produtor de instalação de lease e ACK se o waiter cancelar.
Shutdown cancela observadores e aguarda produtores existentes, inclusive
quando quem aguarda o próprio shutdown cancela. Não há tarefa por operação
recebida; os consumidores futuros do daemon usarão as filas limitadas.

## Correção revelada pela integração

A primeira jornada instalada passou, mas sua repetição revelou uma corrida:
`lease.applied` estava no WSS e o receipt HTTP chegou antes do commit dessa
aplicação no Server. O ingresso recusou corretamente o receipt sem dispatch
associado à lease aplicada. A correção fica no Connector: após instalar no
Core e enviar o ACK, repete a mesma requisição de lease no mesmo socket e
exige a mesma resposta. O processamento ordenado confirma o commit do ACK.
Não há nova lease, novo serial, novo request ID ou reancoragem do prazo local.

O teste de contrato mantém essa confirmação bloqueada e verifica que a chamada
não termina antes dela. A solução não acrescenta sleep à jornada nem enfraquece
a validação do receipt. Uma confirmação ausente ou divergente fecha o canal e
mantém a necessidade de reconciliação.

## Evidência

- 13 casos de contrato/ciclo de vida passaram no Connector após a correção.
- 28 casos passaram com Nexus, Connector e Core instalados, `python -I`, fora
  dos clones, com bytes conferidos contra os wheels e as fontes aplicáveis.
- A nova jornada pública passou também no ambiente Nexus: Server uvicorn e
  cliente Connector em WebSocket real de loopback, registro/binding/grant/
  admissão públicos, Core, cinco ações e receipts HTTPS. Confirma uma tentativa
  por operação e sessão fechada. O peer nativo e a qualificação são sintéticos.
- A regressão completa e seus skips ficam no [manifesto coordenado](test_runs_20260930_connection_owner.json).

As campanhas se sobrepõem. Foram preservadas a falha de coleta com Core global
antigo, a correção de import do helper de teste, fixtures incompatíveis com o
schema/API Core e a corrida real observada na campanha instalada. Os registros
históricos permanecem vinculados aos artefatos usados em cada etapa.

O wheel Core permanece `0.2.28.dev0`, com hash
`27df75100dea033ca5456f2d571eb41b6311fa3ce530a723ecd6c606d257953c`.
O Nexus não recebeu alteração de produção neste incremento; usa o wheel do
dispatcher anterior. O Connector recebeu um wheel novo, registrado no manifesto.

## Continuação obrigatória

Ligar o owner à seleção R4 do daemon e ao StateStore, persistir executores e
bindings, resolver a realização física aprovada e despachar para o Core pelos
consumidores produtivo/controle. O daemon ainda usa seu transporte legado;
o novo owner foi exercitado diretamente pela integração técnica.

Completar reconciliação não vazia/paginada, rotação/renovação de credenciais,
eventos/notificações, receipts recuperáveis, governança das sete ações, owner
embedded, limites globais/shutdown, UI/CLI, idioma e aceites de provider/SO/hosts.
Frames ainda não suportados fecham este canal preview. A fila tem limites,
mas isso não qualifica watchdog, consumo global ou storage indefinidamente
bloqueado. Nenhum flag de prontidão foi promovido.
