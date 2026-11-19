# SI-012, SI-025 e SI-036 · Fila e conversa do Pi na Home

No Edge 157 em Windows, com o Nexus e o Connector em loopback e o processo real do Pi 0.87.1, enfileirei duas mensagens na mesma sessão. A 360 px, a revisão da primeira mostrou o texto exato, colocou o foco em Cancel review e permitiu confirmar pelo teclado. O Nexus registrou uma reorientação para o turno ativo. O painel mostrou primeiro a espera pela fronteira do Pi e depois a aplicação da reorientação. A segunda mensagem continuou na fila e entrou em um turno separado.

Na primeira execução, os dois turnos terminaram com sucesso, mas suas respostas ficaram ausentes da conversa. O Core agora publica a identidade nativa de cada mensagem retida no histórico do Pi. A projeção usa a entrada nativa e sua operação canônica e aplica a sanitização existente. Comparei as seis entradas de usuário e assistente da conversa com os IDs exatos do histórico nativo. O teste de regressão também verifica que mensagens distintas com texto igual permanecem distintas.

No novo teste do pacote, a conversa exibiu as duas respostas uma vez cada e preservou o texto e o foco do campo enquanto elas chegavam. Results exibiu dois cards com os horários formatados. O primeiro detalhe abriu pelo teclado. Uma tentativa de clique nesse botão atingiu o tempo limite na largura móvel. A suíte focada dos pacotes teve 70 testes aprovados no Core, 41 no Connector e 46 no Nexus. O fechamento canônico da sessão temporária foi bem-sucedido. O Pi usou um provedor simulado e a rede externa ficou desabilitada.

O resultado cobre essa versão instalada do Pi e essa sequência no navegador. Mensagens antigas sem identidade seguem fora da projeção. Zoom a 200%, leitor de tela, aceite humano e qualificação com provedor real permanecem em aberto. Não há migração. Para reverter, reverta em conjunto a projeção no Nexus e os pins do Core no Nexus e no Connector. Os eventos já gravados ficam no histórico.

[Registro de evidências e hashes](si036-pi-browser-queue-transcript.json)
