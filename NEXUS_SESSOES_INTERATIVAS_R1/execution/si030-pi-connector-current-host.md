# SI-030 · Sessões independentes com Connector nesta máquina

Nexus, Connector e Core foram instalados a partir dos wheels em um diretório descartável no Windows. O Connector se vinculou ao Nexus por loopback em um projeto temporário. O terminal ConPTY abriu o Pi 0.87.1 e manteve a sessão de origem, seu rascunho e sua fila ao revisar a abertura de outra sessão. A sessão nova só foi admitida após a confirmação explícita. [Evidência estruturada](si030-pi-connector-current-host.json)

A fixture descartou a resposta HTTP depois da admissão. O terminal recuperou o recibo original, mostrou o comando da nova sessão e anexou ao segundo processo Pi. A abertura ficou registrada uma vez. A sessão vazia ficou sem turno. Na sessão de origem, a entrada enfileirada foi entregue uma vez e a geração do Connector e as revisões de autorização permaneceram iguais. O fechamento canônico encerrou os dois processos. O banco passou na verificação de integridade, com dois resultados e nenhuma violação de chave estrangeira.

Passaram o ensaio nativo e 14 regressões instaladas de registro, renovação, revogação e apresentação de sessões. A primeira rodada expirou durante a observação do recibo da abertura inicial. O pedido original ficou em reconciliação na base descartável. A rodada concluída usou outro projeto e ampliou o prazo de observação da fixture. As respostas vieram de um provedor sintético com a rede do Pi desabilitada.

A etapa acompanha a decisão de testar o Connector nesta máquina e adiar a qualificação adicional no macOS. O cenário entre máquinas permanece `NOT_RUN`. A mudança de fixture dispensa migração. O rollback reverte os commits de teste e de evidência. [Escopo deste corte](si041-qualification-checkpoint.md)
