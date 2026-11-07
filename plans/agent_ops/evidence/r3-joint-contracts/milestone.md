# R3 — contratos conjuntos no pacote instalado

71 identidades únicas aprovadas: RG-01/02/11 (9), RG-03 (6), RG-04 (17) e recuperação selecionada RG-05 (39). Dez casos são novos; os demais reutilizam testes existentes. Reruns e rodadas iniciais não são somados. `integration.json` liga cada identidade ao XML de aprovação.

Os testes usam os wheels atuais Nexus 0.3.3, Connector 0.0.12 e Core 0.0.14 com MCP 1.30.0 na venv CI isolada cuja resolução e `pip check` estão retidos em `../r3-qualification-readiness/ci/reports.json`. Os 690 arquivos do pacote Nexus continuam byte a byte iguais entre checkout, wheel e instalação; não houve alteração de produto.

RG-01 valida dois participantes MCP autenticados e um runtime no mesmo workspace, mensagens e resultado canônico sem duplicação. RG-02 disputa BROADCAST com MCP primeiro, runtime primeiro e corrida; há um vencedor/epoch/efeito. RG-03 preserva prioridade, FIFO, fairness, opt-in, audiência e reserva Core durante observação idle; TTL diminui sem renovação. RG-04 mantém shared/per_sender/per_sender_session/one_shot. RG-11 mantém entrega exclusiva entre push runtime e pull MCP, incluindo HTTP/WSS loopback.

As duas construções manuais de DaemonApp na fixture remota recebem gerações sintéticas distintas para seu recibo de shutdown. O fluxo público atribui isso em run_forever, que a fixture não executa. Shutdown e assertions permanecem ativos. Não foi demonstrado defeito do Connector.

Falhas iniciais permanecem preservadas: parâmetro idempotency_key indevido no claim MCP; comparação do TTL remanescente como constante; cleanup da fixture sem generation. Imports de fixture foram ajustados para Ruff e os seis casos RG-03 requalificados nos bytes finais. Os dois arquivos novos passam Ruff integral; não se declara lint global limpo do helper antigo.

RG-05 permanece em progresso: 39 casos verificam recuperação sem replay para work/decision, participant init/launch, coordenação/cooperação, bootstrap remoto e Finish. Doubles e fronteiras reais estão discriminados em recovery/reports.json; não certificam todos os caminhos ou quedas reais de serviços/provedores.

RG-06 permanece em progresso: 131 módulos Core atuais importados sob guards sem eventos negados; arquivos de origem/wheel/instalação iguais. O resumo observado é manual, sem stdout bruto local; não cobre qualquer leitura de ambiente nem API nativa de credenciais. AST literal de 513 arquivos Nexus e 122 Connector não encontrou import entre aplicações; essa verificação das aplicações não cobre imports dinâmicos. Auditoria em core/.

RG-01/02/03/04/11 ficam verificados no escopo canônico Windows com peers nativos sintéticos. Não são dois executáveis MCP reais, inferência de provedor, serviço registrado, M1/M2 ou aceite global R3. RG-07, rastreabilidade final, revisão de artefatos e campanhas reais continuam abertos. O plano fixo e seus conjuntos de 59/132/28/17 IDs permanecem iguais.

Somente arquivos públicos enumerados foram copiados; homes, bancos, cofres e tokens de fixture ficaram fora. Manifests originais e falhas históricas são imutáveis. O manifesto deste diretório conserva hashes exatos.
