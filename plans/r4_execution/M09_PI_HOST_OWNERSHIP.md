# M05/M06/M09 — posse da bridge Pi nos hosts

## Implementação

O Core 0.2.30.dev0 fornece PiNativeActionOwner como hook público de lançamento.
O owner exige a instalação Pi, a referência preparada da capability e o
contexto atual antes e depois de iniciar o listener. Cada sessão recebe um
listener loopback próprio, iniciado uma única vez. O Core continua sem
implementar o domínio de handoff ou transportar o token HTTP bruto ao filho.

NativeActionSocketService passa a acompanhar separadamente os observadores
de socket e os produtores de domínio. Timeout da resposta e cancelamento
de quem aguarda o fechamento não cancelam uma mutação já admitida.
Produtores retidos continuam contando no limite de admissão. O fechamento
impede novas chamadas, fecha os sockets e só confirma conclusão quando os
produtores terminam. Resultado incerto de mutação conserva o operation_id.

O CoreRuntimeHost do Connector e o EmbeddedRuntimeHost do Nexus compõem
esse hook pela API pública create_runtime. Factories dos backends canônicos
congelam a capability/escopo e consultam a lease atual. Configuração de bridge
em candidato diferente de Pi é recusada. Reutilizar runtime com outro factory
não substitui silenciosamente a capability.

R4LaunchSetup encaminha o factory pelo owner de execução do Connector.
EmbeddedExecutor também o conserva ao adquirir o runtime e ao preparar a
abertura. O fechamento explícito cerca o ingresso, e o shutdown dos hosts
mantém runtime, journal e ledger quando há produtor de domínio pendente.
O shutdown embedded libera seus registros resolvidos, incluindo o factory.

## Teste integrado com processo filho

A campanha usa o adapter Pi RPC copiado do Core, criação real de processo
Node sob contenção e a extensão local incluída no wheel. O CLI técnico
responde ao handshake e, ao receber um turno, chama as três ferramentas da
extensão. A chamada atravessa socket, bridge e backend embedded/HTTP até os
casos de uso reais do Nexus. O teste observa claim único, replay sem segundo
efeito e conclusão do mesmo handoff.

A configuração do processo passa pelo child_environment público. O teste
confirma que o token bruto não chegou ao ambiente do filho e a referência
nativa não foi colocada em argv. A capability permanece no backend confiável.

Uma segunda jornada retém a resposta depois do commit do claim. O processo
é encerrado, mas o host informa posse desconhecida e não fecha o journal.
Após liberar a resposta, uma nova observação de shutdown encerra os recursos.
Os casos são executados para os dois hosts. A campanha embedded também é
executada recusando todos os imports do aplicativo Connector.

## Alcance e pendências

Os hosts recebem factories explicitamente compostos com capabilities aprovadas.
Isso não é a composição automática de produção do daemon ou do Server.
A qualificação do binário e READY do Server são fixtures; o CLI técnico não é
um provider real. O teste não encerra onboarding, perfil/configuração aprovada,
intenção durável de segredo, renovação/rotação, reconciliação não vazia, inbox,
causalidade completa, UI/CLI ou a matriz de providers/SO/hosts.

Os mesmos bytes do Core são fixados nos dois consumidores. A
[evidência](test_runs_20260930_pi_owner.json) identifica artefatos, comandos,
falhas de ambiente de teste e limites. A campanha inicial Connector foi
executada por engano em um ambiente sem pytest-asyncio; a repetição no
ambiente com o plugin executou os casos normalmente.

As flags de prontidão continuam falsas e nenhum gate G0–G3 ou milestone
integral é encerrado por este incremento. Os assets UI preexistentes continuam
fora do commit; o wheel técnico Nexus que os inclui não é uma release limpa.
## Resultados instalados e limite da topologia

Core: 143 passes. Connector: 264 passes e um skip existente. Nexus: 33
passes. A prova embedded com import guard: dois passes. As campanhas
se sobrepõem. O runner verifica 482 arquivos de pacote contra os bytes
dos wheels e das fontes antes de executar os testes.

A fixture embedded prepara autoridade por WSS. Isso não estabelece o
aceite do produto local sem WSS; P5 ainda precisa percorrer onboarding,
admissão e lease locais pelas entradas públicas. Os testes desta entrega
provam o child Pi, a extensão empacotada, o domínio e a retenção de recursos.
