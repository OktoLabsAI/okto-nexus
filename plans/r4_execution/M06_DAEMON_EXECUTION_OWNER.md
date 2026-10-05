# Consumidores de operações sob ownership do daemon — parcial M04/M06

O Connector transfere a execução do teste para `R4ExecutionOwner`, adotado
por `DaemonApp.own_r4_connection`. O owner recebe as reservas do reader WSS,
mantém consumidores separados para trabalho e controle e preserva o produtor
até terminar a execução e a publicação do receipt. O shutdown do daemon
observa esses produtores antes de fechar o Core e os journals compartilhados.

A abertura usa a seleção física aprovada, revalida a lane após esperas,
instala a lease inicial no Core e só então executa prepare/open. Mode/model
vêm do envelope validado; ambiente e referências de credenciais vêm das
portas de composição do host. IDs, targeting, motivo e hash da operação são
preservados pelos argumentos tipados e pela projeção pública de receipts Core.

Os sete verbos têm tradução: open, submit, steer, interrupt, close, approval
e input. Para input protegido, o host resolve a referência e o Core verifica
o digest; o contexto é revalidado após essa espera. O Core exige que o pedido
nativo tenha sido observado antes da aplicação da decisão.

Falha de execução/publicação encerra a conexão e mantém o erro observável.
O consumidor não repete o efeito nem cria outra intenção. O Core conserva
seus fatos duráveis; completar a recuperação/publicação desses fatos continua
em M07. Não há receipt de sucesso fabricado para uma exceção.

## Prova e limites

A jornada pública WSS agora admite intenções via HTTP e consulta as mesmas
operações até observar seus receipts. O teste não chama prepare/open/control
nem projeta/publica o receipt: esses passos pertencem ao consumidor do daemon.
São confirmados uma abertura na pasta aprovada, cinco operações com um envio
cada, sessão fechada e shutdown do host. A conexão ainda é negociada pelo
fixture, com ambiente vazio e provider/qualificação sintéticos.

Testes dirigidos exercitam controle enquanto a publicação produtiva espera,
cancelamento do waiter de stop, invalidação durante setup, perda de publicação,
entrada imutável, controles tipados, open duplicado, namespace cruzado e uma
aplicação nativa de approval/input. Os resultados e tentativas estão no
[manifesto coordenado](test_runs_20260930_execution_owner.json).

| Campanha | Resultado |
|---|---|
| Connector, regressão completa | 286 passes, 2 skips |
| Connector, contratos e consumidores | 17 passes |
| Nexus R4, fonte | 103 passes |
| Wheels instalados fora dos clones | 63 passes |

Os grupos se sobrepõem. As falhas iniciais foram preservadas: fixtures de
receipt/close e ordem de cleanup, além de uma corrida real na observação de
produtores concluídos durante stop. O wheel final Connector é identificado
pelo SHA-256 `1ff0de4fa9dac562a834c91431ef4d2cc113f899cf921295e37acf6a539f42bf`.
O Core continua no mesmo wheel `0.2.28.dev0`; suas fontes não mudaram.

O owner tem até dois produtores ativos e 64 sessões rastreadas; o daemon admite
até 32 conexões R4. Reservas continuam limitadas pelo reader. Sessões fechadas
ou incertas permanecem rastreadas; o limite recusa novas aberturas. Duplicidade,
transporte legado simultâneo, canal indisponível e draining recusam adoção.

Ainda faltam startup automático R4, registro persistido de executor,
credenciais/reconnect/renovação de tickets e leases, refresh de revisões,
perfil/ambiente/capability de produção, reconciliação não vazia e publicadores
duráveis. Ingresso canônico de pedidos nativos e UI/CLI de decisão pertencem
à integração M08/M10. A serialização dentro de cada classe de fila precisa
das provas de fairness/latência M11, assim como o prazo global de shutdown e
ownership de recuperação quando o resultado fica incerto.

O incremento não aceita daemon completo, processo/host independente, provider
real, Linux, embedded ou gate final. Nenhuma flag de prontidão foi promovida.
