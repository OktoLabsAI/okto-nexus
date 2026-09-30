# Registro durável do executor pela CLI Connector — parcial M02/M06

O Connector passa a persistir a intenção e o resultado do registro R4 no
schema 5. O registro mantém Server, Connector, agente escolhido, corpo/ID da
intenção e executor canônico. O ticket de bootstrap fica apenas em memória.
Repetir após perda de resposta usa a mesma intenção e recupera o mesmo executor.

O serviço verifica `/me`, identidade e revisões canônicas do ticket retornado,
além de aplicar CAS contra o perfil, credencial e intenção locais. Mudança
concorrente ou resposta de outro escopo não substitui o registro. O prazo local
do ticket começa antes do HTTP, sem ganhar tempo após a resposta ou persistência.

A CLI oferece `executor register`, `executor list` e `executor show`. O comando
`identity add` também passou a guardar o perfil do Server autenticado, usando
o mesmo caminho já empregado por `connect`. Todos os textos novos são US English.

## Jornada e evidência

O teste `test_executor_registration_cli.py` invoca a entrada real da CLI contra
um Server HTTP em loopback. Importa identidade, registra, repete, lista, consulta
e solicita novo bootstrap a partir do estado reaberto. Confirma um executor
canônico, uma intenção de registro e ausência de tickets/keys no estado público
e na saída CLI. O executor continua `DISCONNECTED`; registro não concede runtime.

Os testes dirigidos incluem resposta perdida, escopo/revisões divergentes,
troca concorrente de identidade/perfil/intenção, conflito no ID retornado,
ticket expirado durante a espera e migração aditiva de schema 4 para 5.
Resultados e hashes ficam no [manifesto coordenado](test_runs_20260930_registration.json).

| Campanha | Resultado |
|---|---|
| Connector completo | 300 passes, 2 skips existentes |
| Connector dirigido | 40 passes |
| Nexus R4 | 104 passes |
| Wheels instalados fora dos clones | 78 passes |

Os grupos se sobrepõem. O Connector publicado é `d1c30e8`; o wheel testado tem
SHA-256 `927bb98c9956fea8f688b972e7b1e2193a437fc07ef16b8c674c8ce103a86a42`.
O Core permanece `0.2.28.dev0`, com o mesmo hash nos consumidores.

## Trabalho restante

O próximo passo é fazer o startup automático do daemon consumir esse registro,
obter o bootstrap e negociar o canal, publicar inventário e anexar bindings.
Renovação de tickets/leases, ambiente/capability de produção, reconciliação,
refresh de revisões e aceites finais continuam pendentes. Este incremento
conclui o pré-requisito persistente e sua entrada CLI, sem declarar essas etapas
posteriores implementadas.

O schema 5 é recusado por binários antigos; backup e ensaio completo de rollback
continuam em M12. Produção Nexus, Core e contrato wire não mudaram. Nenhum gate
ou flag de prontidão foi promovido.
