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
