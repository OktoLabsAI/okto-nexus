# SI-038 · Primeira campanha com Codex no Windows

O candidato é o Nexus `c018d7d4`, com os wheels fixados do Connector 0.0.15 e do Core 0.0.16. O app-server 0.157.0 é o executor qualificado para conversa e reorientação neste build. O Codex 0.170.0 é o visualizador revisado. A campanha mais antiga do plano Nexus UI recebeu `modelNotFound` para `gpt-5.3-codex` durante o teste de conexão. O mesmo nome está ausente do catálogo que o app-server 0.157.0 reportou no ensaio com perfil vazio e proxy de descarte. A observação com perfil vazio pode usar catálogo local. [Falha anterior](../../NEXUS_UI_R1/execution/pr07-native-codex-only-v2-carry/execution-terminal-ro.json) [Matriz dos builds](si039-codex-build-capabilities.md)

## Ensaio com o pacote atual

O Edge e o ConPTY completaram a jornada de terminal, fila da Home, reorientação e desanexação com o app-server real e um simulador de respostas em loopback. A mesma thread ficou em um único processo e recebeu três turnos e uma reorientação. Uma leitura somente leitura do journal correlacionou quatro atualizações cumulativas de consumo sintético com os três turnos. A reorientação compartilha a contagem do turno ativo e seu recibo continuou em `DISPATCHING`. O produto registrou os três resultados e os dois visualizadores desanexados. O fechamento canônico encerrou o app-server e a verificação liberou o listener.

Passaram a jornada no navegador e 74 regressões instaladas do CLI, da anexação e da fila. As primeiras rodadas ajustaram o cofre sintético para a lista de variáveis admitidas pelo Connector e separaram a abertura do navegador do roteiro que espera o turno ativo. A preparação usou apenas dados descartáveis, sem credenciais, inferência externa ou alteração da instalação pessoal. Reverter o marco dispensa migração. [Observações e hashes](si038-codex-campaign-preflight.json)

## Consulta da conta

Após consentimento para a consulta, inicializar um único app-server do build fixado com o perfil Codex já autenticado e um projeto descartável. Usar `account/read` com `refreshToken: false` e `model/list` com paginação limitada. O transporte encerra ao fechar o próprio stdin. Registrar só a presença de conta, os nomes e o modelo padrão reportados. A disponibilidade de inferência exige a confirmação do teste canônico. A autorização para essa consulta cobre exclusivamente as leituras descritas.

## Jornada proposta para qualificação

1. Após autorização específica do modelo, do candidato e do orçamento, fazer o teste de conexão canônico no projeto temporário. Exigir terminal de sucesso, evidência de consumo associada ao turno e recibo de setup confirmado antes de executar `connect --no-interactive`.
2. Na Home, enviar um pedido de resposta curta e abrir a sessão exata como leitor no terminal. Desanexar antes do fim e retornar à mesma conversa na Home. Provar a continuidade pelo ID nativo, pela geração do dono, pelo processo do app-server, pelo prompt registrado uma vez e pelo resultado canônico.
3. Executar `connect -i` com a mesma conexão e selecionar o alvo exato. Adquirir a escrita de forma explícita e iniciar um turno na interface nativa. Durante o turno, enfileirar a mensagem padrão na Home e confirmar a reorientação do turno pelo Nexus CLI. Desanexar os visualizadores, conferir o recibo na Home e deixar a entrada enfileirada iniciar um turno separado depois do término.
4. Correlacionar os efeitos e seus recibos com a mesma sessão em cada transição. Comparar a Home, os eventos do app-server e o journal do Connector. Fechar canonicamente a sessão e confirmar o encerramento do app-server, dos visualizadores e do listener descartável. Preservar os dados para auditoria se algum resultado ficar incerto.

O ensaio em loopback libera as respostas em pontos controlados. Para a campanha, preparar no projeto temporário um comando local de leitura que aguarde um marcador por tempo limitado. Validar esse fluxo em ensaio separado antes de consentir a campanha. Se o provedor concluir o turno antes da janela de observação, registrar o cenário como inconclusivo e parar. Os prompts e a revisão devem usar só dados sintéticos, com automações externas e MCPs globais desabilitados.

## Limites propostos

- Cinco admissões explícitas no máximo. Uma para setup, uma para a Home, uma para a entrada nativa, uma para reorientação e uma para a saída da fila. Reservar o turno da fila quando a entrada for aceita, pois o despacho é automático depois do turno ativo.
- Provisão permanente de 75 mil tokens por admissão. Teto proposto de 500 mil tokens observados, com parada preventiva antes de 450 mil. Para turno ativo e reorientação que compartilham contador, comparar o delta observado com a soma de suas provisões. Para passos com contador próprio, debitar o maior valor entre provisão e consumo observado. Leituras atrasadas e chamadas internas podem ultrapassar o teto observado.
- Uma tentativa por efeito. Falha, consumo sem correlação, reconhecimento perdido ou divergência no modelo encerram novas admissões. Conservar a provisão já tomada e reconciliar o resultado antes de fechar. Sem substituição automática de modelo ou conta.

A preparação não altera o estado de SI-T-I07, SI-T-I08, SI-T-I09 ou dos gates por harness. Ativação de outros harnesses e sistemas operacionais requer evidência própria.
