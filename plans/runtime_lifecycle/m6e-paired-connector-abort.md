# M6e — instalação pareada interrompida pelo orçamento de memória

Data: 2026-10-19 (UTC). Checkpoint de preparação M6, sem decisão de adoção.

Um Connector descartável anterior não podia ser usado na comparação: seu journal
retinha a claim não liberada `ses_752bbbd81a354e5ddfc6425781c811a6`, ausente
dos dois homes descartáveis examinados. O Server recusou a reconciliação com
`4406` corretamente; não há prova para descartar possível efeito. O estado foi
preservado sem limpeza ou reparo presumido.

Criei pela UI do Nexus instalado um agente remoto novo `m6e-pi` no workspace
M6D e configurei one-shot com 2 instâncias paralelas e 1 aquecida, para comparar
com o Pi local `m5m-pi-new` configurado do mesmo modo. Importei sua chave de
uso único no vault privado de um Connector novo, com estado separado em
`okto-nexus-connector-m6e-20261019`; removi os snapshots temporários que
continham a chave. A CLI configurou Pi 0.87.1 com a mesma instalação, workspace,
diretório local e login de provedor do teste M6d. A solicitação R4 foi aprovada
pela UI. O controle teve um fechamento `4403` transitório no instante da
aprovação e voltou automaticamente a `CONTROL_READY`; o binding ficou
`APPROVED`, `attached=true`, e o agente `CONNECTED` sem intervenção.

Antes da primeira mensagem, a memória livre passou de aproximadamente 5,4 GiB
para 3,17 GiB. Isso ficou abaixo do piso de 4 GiB fixado no plano. A comparação
de carga, respostas, reinício e revogação **não foi executada**. Parei o daemon
pela CLI autenticada e o Server descartável por sua sessão de controle; fechei
o navegador de teste. Ao final, não restavam processos `okto-nexus*`, a porta
8204 estava livre e havia 4,6 GiB disponíveis. O Nexus global permaneceu parado.

Este checkpoint comprova somente onboarding, aprovação e reconexão do controle
na transição inicial. Não altera o aceite M6 nem prova superioridade do
supervisor separado. A próxima tentativa de carga deve ocorrer com folga real
acima do piso, sem ampliar os critérios da comparação definidos no ADR M6.

Uma segunda tentativa no mesmo dia começou com 7,93 GiB livres. Após iniciar o
Server descartável, a UI e o Connector pareado, a memória caiu para 4,04 GiB,
novamente antes de uma mensagem de teste. O controle voltou a `CONTROL_READY`
e o binding ficou conectado. A CLI informou transporte IPC `loopback` nessa
inicialização; portanto ela não qualifica o adaptador experimental de named
pipe. Parei os três componentes, sem encerrar processos Claude/Codex que
pertenciam a outras sessões do usuário. Não houve execução real nem medição de
latência nesta segunda tentativa. Porta 8204 e processos de teste ficaram
ausentes após a parada.
