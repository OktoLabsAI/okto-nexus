# SI-036 · Ensaio do ambiente para o participante

O ensaio automatizado usou um wheel construído a partir da branch publicada `feature/v0.3.8`, na revisão `e286762f`. Um pedido de revisão de remessa foi enviado pela API normal antes de o navegador abrir. O projeto já estava selecionado na Home e o Pi já atendia o pedido quando a primeira tarefa começou. Essa preparação evita que participante tenha de escolher uma versão da Home, configurar um harness ou criar o trabalho inicial.

A automação no Edge encontrou o texto do pedido pelo card, colocou o pedido de conferir o endereço na fila e retornou pelo mesmo card. O Nexus registrou um único envio para o próximo turno. As duas respostas apareceram na ordem na mesma sessão, e o processo Pi saiu após o encerramento canônico. O ambiente descartável usou Pi 0.87.1 e respostas determinísticas, sem chamadas externas. [Resultados e hashes](si036-participant-rehearsal.json)

Na rodada humana, o facilitador abre a Home já preparada e apresenta uma tarefa por vez. A primeira pede que a pessoa explique o que o colaborador está atendendo. A segunda pede que envie **Confira também o endereço de entrega** e diga o que a tela indica sobre o momento da resposta. A terceira pede que volte à Home, encontre a conversa e identifique os dois resultados. A primeira resposta fica retida até a pessoa relatar o que entendeu da fila e retornar à conversa. O texto do pedido inicial só aparece no cenário, para que a pessoa o encontre na interface.

O aceite humano continua pendente. Esta etapa atualiza evidências, dispensa migração e pode ser revertida pelo commit de registro.

## Revalidação do candidato atual

A revisão `579bdef6` passou no Edge com o dashboard do wheel e o Connector em loopback nesta máquina. A Home abriu com o projeto selecionado e mostrou **Revisão de remessa** em andamento. O ensaio colocou a mensagem seguinte na fila, saiu do painel e voltou pelo mesmo card. A conversa exibiu as duas respostas, cada uma uma vez. O banco confirmou uma sessão, dois resultados e nenhuma violação de chave estrangeira. O encerramento confirmou a saída do Pi, o fechamento do listener descartável e a remoção do arquivo temporário de autenticação do navegador. [Resultados e hashes](si036-participant-rehearsal.json)

O roteiro humano foi sincronizado com os mesmos wheels e a mesma preparação do projeto. A revalidação acima é automatizada. O aceite do participante continua pendente.

## Revalidação em `b4bb0031`

O Edge repetiu a jornada com o dashboard empacotado, Pi 0.87.1 e Connector na mesma máquina Windows. O roteiro selecionou **Projeto Remessas** e confirmou que **Assistente de remessas** já exibia atividade na Home. A automação encontrou o pedido, enfileirou a mensagem seguinte, reencontrou a conversa pelo mesmo card e conferiu as duas respostas na ordem esperada.

A auditoria verificou uma abertura nativa, dois resultados da mesma sessão e um fechamento canônico. O servidor descartável saiu e o arquivo temporário de autenticação foi removido. A primeira rodada abriu o navegador, mas o processo de lançamento bloqueou o roteiro. Na rodada aprovada, a abertura do Edge e as interações ocorreram em processos separados.

O cenário usa respostas simuladas em loopback. O aceite do participante e a validação com leitor de tela no Windows permanecem em aberto. A atualização de evidências dispensa migração. [Comandos, resultados e hashes](si036-participant-rehearsal.json)

## Jornada até a coluna Results

O ensaio automatizado usou o dashboard empacotado do Nexus em `93e89777`, Edge 158, Pi 0.87.1 e Connector nesta máquina Windows. Com **Projeto Remessas** selecionado, o navegador encontrou o pedido de revisão em andamento, enfileirou a mensagem seguinte e retornou à mesma conversa pelo card. Enquanto a primeira resposta estava retida, a entrada permaneceu na fila. Depois da liberação, as duas respostas apareceram uma vez e na ordem esperada.

Ao fechar o painel e atualizar a Home, as três colunas estavam visíveis. **Results** mostrou dois botões **View result** com horários em formato legível. A auditoria confirmou uma abertura nativa, dois turnos e um fechamento, com as duas respostas na mesma sessão e a entrada da fila em `ACCEPTED_NATIVE`. O SQLite passou nas checagens de integridade e de chaves estrangeiras. O processo do Pi, o listener e o perfil descartável do navegador foram encerrados.

A abertura do Edge manteve o comando de lançamento ativo. A automação prosseguiu em outro processo, com uma única execução do roteiro sobre a sessão já aberta. O ensaio usou respostas simuladas e não substitui o aceite do participante. O registro dispensa migração e pode ser revertido pelo commit. [Comandos, versões e hashes](si036-participant-rehearsal.json)

## Abrir cada resposta depois do encerramento da sessão

No dashboard anterior, cada botão **View result** direcionava o Edge para uma operação diferente da mesma sessão encerrada. O painel mostrava a conversa, sem identificar a resposta do card selecionado. A primeira passagem reproduziu a falha em um card. A segunda verificou os dois após o roteiro passar a reconhecer o botão com foco.

No novo wheel, **Selected result** apresenta a resposta retida da operação escolhida antes da conversa. O Edge 158 para Windows abriu os dois cards, conferiu o texto de cada resultado no próprio painel, encontrou uma região de conversa em cada abertura e devolveu o foco ao botão ao fechar. O mesmo teste de regressão do componente falhou antes da correção e passou junto com os 424 testes do frontend. O build do Vite e a validação do wheel e do sdist pelo Twine também passaram.

O ensaio usou duas cópias descartáveis do banco deixado pelo Pi e pelo Connector já encerrados. A auditoria preservou o banco original e os registros de sessões, operações, fila e resultados. A rodada dispensou inicialização do harness e chamadas ao provedor. A mudança está no dashboard do Nexus, dispensa migração e pode ser revertida pelo commit que atualiza o componente e o bundle. O aceite do participante e a confirmação da fala por leitor de tela no Windows permanecem pendentes. [Evidências e hashes](si036-participant-rehearsal.json)

## Jornada completa no wheel com a inspeção corrigida

No Windows, o Edge percorreu a jornada a partir do pedido inicial no Nexus `f2bbb856` instalado. A automação encontrou a atividade na Home, enfileirou a segunda mensagem enquanto o Pi atendia a primeira e reabriu a mesma conversa. Em Results, abriu cada card e conferiu a resposta antes da conversa. O foco voltou ao botão após cada fechamento. O registro do navegador foi conferido contra os dois resultados no SQLite, pelos IDs exatos da operação e da sessão.

O Pi 0.87.1 usou o Connector R4 nesta máquina e respostas simuladas. A auditoria confirmou uma abertura nativa, dois envios e um fechamento. A entrada da fila atingiu `ACCEPTED_NATIVE`, o processo do Pi saiu e o listener fechou. O primeiro roteiro do navegador atingiu o limite de espera antes de navegar. A segunda execução aproveitou o ambiente nativo que ficou pronto logo depois, com a mesma sessão do navegador e sem repetir o trabalho inicial.

O marco acrescenta evidência do fluxo completo, dispensa migração e pode ser revertido pelo commit de registro. O aceite do participante e a confirmação de fala no Windows seguem pendentes. [Resultados e hashes](si036-participant-rehearsal.json)

## Disponibilidade de continuar a sessão

O painel usa o estado atualizado da sessão para oferecer **Continue this exact session**. Sessões encerradas, em encerramento, sem controle ou com liberação pendente continuam disponíveis para leitura do histórico e dos resultados. Ao selecionar a ação, o fluxo existente revalida a mesma sessão.

O Edge abriu os dois resultados no wheel atualizado e exibiu a resposta de cada operação acima da conversa, com retorno de foco ao fechar. O botão deixou de aparecer para a sessão encerrada. O ensaio usou uma cópia do banco produzido pela execução anterior com Pi e Connector. Passaram 425 testes do frontend, incluindo a renderização da ação para uma sessão disponível. O build e a validação estrita do Twine também passaram.

O wheel conserva os 815 arquivos do pacote fora da troca do HTML e do JavaScript do dashboard. A alteração dispensa migração e pode ser revertida pelo commit. O aceite do participante e a validação de fala no Windows seguem pendentes. [Resultados e hashes](si036-participant-rehearsal.json)

## Rodada com participante no Edge

O ambiente começou com **Projeto Remessas** selecionado e um trabalho em andamento. O participante encontrou o pedido em **Working** e confirmou o texto da primeira mensagem. Também conseguiu identificar a atividade pela saída do harness. Ao abrir o painel, relatou excesso de metadados e seletores, além de dificuldade para entender que **Technical activity** mostrava a saída do console. O envio pareceu depender de configurações de conexão que o participante esperava que a Home resolvesse automaticamente.

O participante enviou a mensagem da segunda tarefa e descreveu o envio como relativamente simples. O SQLite registrou a entrada da web como `turn.steer` em `DISPATCHING`, durante o turno original. O cenário avaliava se o envio comum ficaria para o próximo turno. A rodada foi encerrada nesse ponto, com a leitura dos resultados ainda por executar. O aceite de usabilidade permanece pendente.

O participante pediu uma tela de console única para digitar e acompanhar a saída do harness, com a opção de destacar a última mensagem do usuário. A próxima decisão de desenho é o grau de integração com a interface nativa do terminal. As novas tarefas deverão confirmar que o usuário pode enviar uma mensagem comum sem reorientar o turno por engano.

A rodada usou o dashboard do Nexus instalado, Edge, Connector e Pi 0.87.1 com respostas simuladas. O fechamento canônico terminou com sucesso, o listener saiu e a sessão temporária do navegador foi removida. O teste de observação registrou a interrupção da rodada como `SKIPPED`. Este registro pode ser revertido pelo commit. [Observações e hashes](si036-participant-rehearsal.json)

## Terminal nativo do Pi na Home

O participante escolheu a interface nativa do harness. A Home abre diretamente a única sessão viva quando o inventário completo da conexão confirma que as demais foram encerradas. Para o Pi, **Follow activity** abre o renderizador e o editor do próprio harness em um terminal no navegador. O Server valida a origem, o login, a geração da sessão e o ticket de uso único. Quando já existe outro editor, o navegador abre em modo de leitura. A revisão final limitou a abertura automática do terminal ao acompanhamento do harness, preservando os fluxos de resultados e decisões.

No Edge para Windows, com Nexus do checkout e Connector e Core instalados nos pins vigentes, a automação encontrou o pedido original no terminal do Pi 0.87.1. Colou a mensagem com acentos e enviou com Enter. O painel confirmou a fila e devolveu o foco ao card ao fechar. O SQLite comprovou um único vínculo de terminal com escrita em `DETACHED`, uma sessão, dois turnos e uma mensagem de `native_terminal` que passou de `QUEUED` para `ACCEPTED_NATIVE`. Os dois resultados ficaram acessíveis depois de **Refresh**. O fechamento canônico encerrou o Pi e o listener. O teste usou respostas determinísticas e consumiu zero chamadas a provedores externos. Também passaram 428 testes Node, 49 testes de transporte, o Ruff e o build do dashboard.

O Pi ainda imprime os metadados de entrega anexados ao pedido original dentro do terminal. A rodada do navegador cobriu o Pi via Connector e o envio comum. Os atalhos de reorientação e interrupção no navegador, o terminal nativo de Codex e Claude, o aceite humano e a fala por leitor de tela seguem pendentes. A primeira leitura dos resultados no navegador precisou de atualização manual. A alteração dispensa migração, mantém os pins do Connector e Core e pode ser revertida pelos commits da seleção de sessão e do terminal. [Evidências e limites](si036-participant-rehearsal.json)

## Console como tela da sessão

Na rodada com Nexus 0.3.8, o participante relatou que o fluxo ainda apresentava os painéis antigos, os controles de sessão e os metadados. A rodada terminou antes do aceite. O Nexus 0.3.9 abre o console em tela cheia a partir do card do harness e do trabalho com sessão conhecida. A Home apresenta o colaborador, o harness e o trabalho, sem IDs de conexão. O console recebe foco para digitação e devolve o foco ao card ao voltar. A escolha de sessão aparece quando existem alternativas ativas e a Home não pode provar um único destino. As aprovações continuam disponíveis em Needs you e no sino.

O Core 0.0.17 mostra no renderizador nativo do Pi o corpo do pedido de entrega. O envelope permanece no contexto do harness. O console aceita mensagens e os comandos `/help`, `/status` e `/interrupt`. A interrupção exige confirmação e usa o controle do turno exato. O transporte também foi testado com comandos indisponíveis, que não entram na fila.

O Edge no Windows mostrou o pedido sem os metadados de entrega e sem abas ou seletores. O ensaio executou ajuda e status, cancelou a interrupção e enfileirou uma mensagem com acentos. O SQLite confirmou que o mesmo Pi 0.87.1, com Connector 0.0.16, aceitou a mensagem no turno seguinte, após fechar o console. A Home mostrou os dois resultados após **Refresh**. O fechamento canônico encerrou o Pi e o listener. As respostas foram simuladas e não houve chamadas a provedores externos. A confirmação da interrupção passou no teste de transporte com admissão simulada. A extensão final da entrada pelo trabalho passou nos testes Node e no build.

As três versões dispensam migração de dados. Para reverter, use o conjunto Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16. A rodada automatizada cobre o Pi. O terminal nativo de Codex e Claude e o aceite humano desta versão seguem pendentes. [Evidências e versões](si036-participant-rehearsal.json)

## Uma única entrada para o console

Na rodada com o wheel 0.3.9, o participante encontrou dois caminhos. O evento de mensagem abria **Activity detail**, com **Conversation**, **Technical activity** e controles da fila. **Open console** abria a moldura do terminal, mas o servidor devolvia HTTP 409 ao preparar a conexão. O SQLite confirmou uma sessão `READY` com lease `ACTIVE` e sem o registro da versão usada no lançamento.

O card mantém o título do trabalho visível e oferece somente **Open console** para acompanhar a sessão. Um link anterior para o mesmo trabalho abre o console ao resolver a relação exata. Quando o vínculo identifica uma sessão e omite o estado, o console consulta o estado canônico antes de anexar. A admissão preserva o registro do build observado quando o inventário foi atualizado de forma compatível para a mesma instalação aprovada. A intenção e a revisão enviadas ao Connector continuam as que foram aprovadas.

Instalei o wheel corrigido em um ambiente descartável e exercitei os dois caminhos no Edge com o Pi real e respostas simuladas. Ambos exibiram o pedido no mesmo console, sem controles do painel anterior. `/status` respondeu na tela, e a mensagem enviada por Enter foi entregue no turno seguinte da mesma sessão. Os dois resultados foram conferidos pelo corpo exato. Passaram 429 testes Node, 11 testes de lançamento e o ensaio com Pi e Connector. O navegador, o Pi e o listener da automação foram encerrados.

A correção do registro vale para novas admissões. A sessão usada na rodada anterior foi encerrada no ambiente de teste. A mudança dispensa migração e pode ser revertida por commit. O aceite humano da versão corrigida continua pendente. [Evidências e limites](si036-participant-rehearsal.json)

## Digitação e entrega pelo navegador

Na janela do participante, o Edge exibia a resposta do Pi enquanto o rodapé ainda mostrava **Message queued for the next turn**. O recibo persistido já estava em `ACCEPTED_NATIVE`. O console agora acompanha o recibo exato do último envio e passa a mostrar **Message delivered to Pi** quando o harness confirma a entrada. A recarga recupera o estado do mesmo recibo. O alerta de saída no console aparece quando há um rascunho editado.

No Edge, com o wheel instalado e o Pi real usando respostas simuladas, a automação digitou `/status` e uma mensagem de duas linhas, corrigiu um caractere com Backspace e enviou com Enter. Recarregou a página durante a espera e após a entrega. O console manteve a mesma sessão e mostrou a resposta e a confirmação atualizada. Depois da recarga, `/status` continuou funcionando na mesma sessão. O SQLite confirmou uma sessão, uma mensagem de acompanhamento e dois turnos. A execução encerrou o Pi e o listener pela via canônica.

### Comandos no console do Pi

Digitar `/` no console exibe os comandos do Nexus disponíveis ali. `Tab` ou um clique completa a entrada e `Enter` executa o comando. A interrupção continua exigindo confirmação no turno exato. Entradas indisponíveis, como `/model`, ficam no editor para correção. A seleção do comando usa o rascunho do editor do Pi e a API libera ao navegador apenas o prefixo da sugestão.

No Edge com o wheel instalado, o Pi 0.87.1, o Connector 0.0.16 e o Core 0.0.17, o ensaio com respostas simuladas abriu as sugestões pelo teclado, completou `/status` com `Tab`, selecionou `/help` com um clique, preservou `/model` no editor após `Enter` e cancelou a interrupção pelo próprio console. O mesmo terminal voltou a receber texto e manteve os recibos de fila e entrega após recarregar. A resposta e o `/status` também continuaram disponíveis. O SQLite confirmou uma sessão, uma entrada entregue ao Pi e dois turnos concluídos. O teste de transporte confirmou que a interrupção só atua após confirmação e que comandos indisponíveis ficam fora da fila.

Passaram 429 testes do frontend, 51 testes do transporte, Ruff e a verificação do lock. O wheel e o sdist passaram no Twine. Wheel SHA-256 `eb3ed86e23d268c87c24b26c4a6187cf69441d96eca65c0d376dbc4b5902a3e9`. O rollback volta ao pacote anterior e dispensa migração. O ensaio automatizado no Windows mantém separada a validação humana.

O console perdeu a conexão uma vez após o ensaio. A ação Reconectar restaurou a escrita na mesma sessão. O Edge registrou 24 mensagens de manutenção da conexão em 125 segundos sem editar o rascunho, e `/status` respondeu ao final desse intervalo. A causa da queda inicial permaneceu indeterminada.

### Terminal de eventos com barra de entrada

A Home voltou a usar o terminal de eventos do Nexus. A mesma tela reúne o histórico paginado da sessão e uma barra inferior para mensagens, reorientação e comandos autorizados no catálogo da sessão. A edição do rascunho acontece no navegador. O envio, a confirmação dos controles e a recuperação de recibos usam os endpoints canônicos. O console também permite verificar uma ação que ficou sem confirmação na apresentação anterior do Pi.

No Edge, com o wheel instalado, o Pi 0.87.1, o Connector 0.0.16 e o Core 0.0.17, a automação abriu a sessão a partir da Home, completou `/status` com `Tab`, preservou o rascunho de `/model`, enviou uma mensagem de duas linhas e confirmou `/steer` na mesma barra. O Pi executou a ferramenta `read` em um arquivo descartável. O terminal exibiu a chamada, seu resultado e as duas respostas simuladas. O recibo de aplicação da reorientação apareceu no navegador e o contexto recebido pelo provedor confirmou o texto exato. Após recarregar, a sessão e o recibo da mensagem permaneceram disponíveis. A barra coube na largura de 390 px. O SQLite confirmou duas entradas na mesma sessão e zero anexos da apresentação direta.

Passaram 429 testes do frontend e 12 testes focados em comandos, reorientação e interrupção. O build, a verificação do lock e o Twine passaram. Wheel SHA-256 `23acbe2c8814554521a1bd1adf5fc92bd4731b5ba61426d92acfb839f1eca090`. O rollback restaura o frontend anterior e dispensa migração. A validação de navegador usou o Pi com um provedor simulado e mantém separada a validação humana.

A Home operacional passou a ser o padrão. A apresentação clássica fica disponível como fallback quando o servidor desativa o recurso. O painel Activity detail exibe o estado e o resultado ou problema, com um botão para alternar entre o console e a conversa da sessão vinculada. No Edge, com registros controlados, foram verificados o padrão com preferência clássica antiga, sucesso, falha, entrega não aprovada e alternância nos dois sentidos. Passaram 430 testes do frontend e o build. O rollback de interface dispensa migração.

Passaram 429 testes Node, o build, a validação estrita do wheel e o ensaio instalado. A mudança dispensa migração e pode ser revertida pelo commit. A rodada de usabilidade continua separada da automação. [Evidências](si036-participant-rehearsal.json)
