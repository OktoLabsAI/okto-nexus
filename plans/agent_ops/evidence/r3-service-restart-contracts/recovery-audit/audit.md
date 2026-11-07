# SVC-T22 / RG-05 — revisão contratual finita

Somente leitura; nenhum teste executado, produto/ledger alterado ou status promovido. Plano fixo SHA-256 `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996` preservado. Referências, hashes, identidades PASS e mapa de assertions estão em `matrix.json`.

| ID | Evidência suficiente já existente | Resto concreto |
|---|---|---|
| SVC-T22 | NS14-01 executa queda abrupta e novo PID do Server no mesmo home. Recupera a mesma operação SUBMITTED/UNKNOWN, claim e reserva do mesmo session_id, slot não liberado e nenhum runtime novo. O helper é idêntico ao retido e a função atual tem a mesma AST histórica. | NS14 usa backend nativo sintético e wheels históricas. Falta qualificar a tentativa de restart com filho físico pertencente ainda vivo; um Python descartável basta. Não é necessário fabricar sobrevivência à morte do pai. |
| RG-05 | As mesmas 39 identidades passam no relatório joint-contract e novamente no instalado cooperative-drain. Assertions cobrem IDs e efeitos únicos nos fluxos novos; AC05 acrescenta mortes reais de processo CLI e emissão/recuperação de grant. NS14 acrescenta restart real com operação incerta. | Encerrar os casos seguros atuais T23/T24 já em andamento e o caso compartilhado SVC-T22 de restart pending com filho vivo. Não foi identificado outro defeito de produto ou necessidade literal de provider/serviço nativo. |

O ramo de operação incerta de SVC-T22 não deve continuar descrito como nunca executado. Sua prova é histórica, identificada como tal; não se transforma em reexecução das wheels atuais.

As 39 identidades são contadas uma vez. O segundo XML coincide integralmente nas 39: Nexus `cd1653db…`, Core `1407014e…`, Connector `73f1a3ba…`. Os testes de bootstrap remoto e lançamento usam doubles declarados; não são processos filhos vivos. As fronteiras reais de CLI/SQLite referenciadas pela matriz AC05 complementam o mapa sem generalizar execução de providers.

No momento desta revisão, o agente responsável informou T23/T24 ainda em execução. Seu cenário mantém um Connector real enquanto dois PIDs do Server se sucedem, mas trabalho e close já terminaram antes da queda. As comparações de operações/recibos e opens/sends=1 verificam ausência de redispatch; não substituem operação incerta nem filho físico vivo. Nenhum PASS futuro foi antecipado.

Recomendação: reter o ramo incerto de SVC-T22 como evidenciado; fechar a lacuna física segura descrita em `technical-plan.md`. Para RG-05, o mapa dos fluxos de recuperação é sustentado pelas assertions e PASS existentes, condicionado apenas ao fechamento das qualificações de lifecycle nomeadas. Provider real, tarefa do Windows e serviço pessoal não são exigências destes dois literais.
