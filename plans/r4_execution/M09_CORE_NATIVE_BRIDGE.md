# M09 — bridge nativa Core nos dois consumidores

## Fronteira implementada

O Core 0.2.29.dev0 aceita a capability de domínio separadamente das sete
operações de runtime da lease R4. A bridge congela o escopo completo e
consulta a autoridade instalada na mesma instância do runtime, com conexão,
geração, revisões e prazo. Sessões inexistentes, fechadas, revogadas,
expiradas ou em renovação pendente não chegam ao backend. Um contexto antigo
não sobrevive à renovação. A autorização também é verificada após o retorno:
uma mutação que pode ter sido aplicada conserva resultado incerto e ID.

O helper público transforma os três requests tipados em JSON limitado,
sem inventar IDs nem executar o domínio. O Connector envia esse corpo à rota
canônica, uma vez, usando exclusivamente a capability nativa. Valida audiência,
escopo, ação, prazo, revisão HTTP, tamanho e correlação da resposta.
Redirecionamento não é seguido; resposta perdida ou inválida não gera retry
automático de mutação. Erros próprios usam US English e não expõem o segredo.

O backend embedded chama o mesmo serviço canônico utilizado pelo HTTP, por
thread de trabalho com UOW próprio, sem depender do aplicativo Connector.
Os dois backends revalidam a capability no Server; a checagem local do Core
não substitui autorização no domínio.

## Provas e alcance

O [manifesto coordenado](test_runs_20260930_native_domain.json) registra
artefatos, campanhas, falhas e repetições. O
[runner instalado](run_native_domain_installed.py) verifica os bytes de cada
pacote contra o wheel e contra a fonte antes das campanhas. Os imports de
produto vêm de site-packages; os testes Core exigem a raiz do repositório
para um import legado entre testes, sem inserir src.

Os seis novos casos Nexus usam uma lease emitida pelo Server e instalada no
Core, handoffs reais do domínio e os backends embedded/HTTP. Cobrem
contexto, claim, conclusão, replay, perda da resposta após commit, revogação
no Server e no runtime. O estado READY do Server e a qualificação do harness
são precondições sintéticas documentadas; o harness é um peer técnico.

As primeiras falhas de campanha foram de infraestrutura de teste: prazo
zero no fechamento de um runtime e resolução de um import legado na execução
isolada. Os registros originais permanecem identificados. Uma invocação de
pytest também apontou um arquivo de socket inexistente e não executou casos.

## Pendências de produto

Este incremento fornece os backends e sua integração testada. A composição
automática pelos hosts ainda precisa de configuração aprovada, referências
protegidas, criação/encerramento do socket Pi e renovação de capabilities.
Também permanecem inbox limitado ao workspace, demais ferramentas, consumo
exclusivo, causalidade completa, reconciliação não vazia, UI/CLI e aceites
reais de provider/SO/hosts.

NS03.04, NS12.01 e NS12.02 continuam parciais. Nenhum marco M00–M13 ou
gate G0–G3 é encerrado; as flags de prontidão permanecem falsas.
Os três assets UI preexistentes estão no wheel técnico Nexus, mas não no
commit deste incremento. O pacote não constitui release limpo nem aceite UI.

## Correção exposta pela campanha ampla

O status IPC do daemon encontrou PermissionError ao abrir state.json durante
uma substituição atômica concorrente no Windows. Passar isoladamente não
descartou a falha: um teste com barreiras demonstrou que a leitura ignorava
o lock do escritor. StateStore.load agora participa do mesmo lock usado por
save/update. O limite de tamanho também é verificado no carregamento interno
de update. Foram acrescentados testes de bloqueio de leitura, concorrência
entre instâncias e limite de tamanho.

Três casos embedded passaram com um import finder que recusa qualquer módulo
okto_nexus_connector. Isso prova a independência do backend de domínio nesta
composição técnica; não substitui o ciclo completo do host embedded.

## Resultado final registrado

Passaram 109 testes no wheel Core, 262 testes no wheel Connector (um skip
existente, identificado no manifesto) e 10 integrações Nexus afetadas no
conjunto final. Os grupos se sobrepõem e não representam requisitos distintos.
A campanha ampla anterior à correção do estado registrou 193 passes e uma
falha; ela não é apresentada como execução completa do conjunto final.
Foram conferidos 482 arquivos instalados contra os wheels e as fontes.
