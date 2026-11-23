# SI-041 · Pausa global com o Pi em execução

O Nexus instalado, o Connector e o Pi 0.87.1 executaram juntos no Windows. O provedor sintético do Pi segurou as duas respostas em barreiras distintas, com a rede bloqueada. No Edge, o operador abriu a conversa exata e enfileirou a segunda mensagem durante o primeiro turno.

1. O Edge ativou **Pause new session messages** nas configurações. A API recusou uma mensagem nova com HTTP 409. A repetição da intenção devolveu o ID e a sequência da entrada já registrada.
2. O primeiro turno terminou durante a pausa. O Connector entregou a mensagem retida à mesma sessão nativa. Enquanto o segundo turno ainda estava em andamento, a conversa no Edge informou que novas mensagens estavam pausadas e o envio estava indisponível.
3. A resposta da segunda mensagem apareceu na conversa antes de reabrir as admissões. O recibo original chegou a `ACCEPTED_NATIVE`. O histórico do Pi continha cada mensagem uma vez. A mesma geração do Connector, o processo do Pi, a sessão nativa e as revisões dos grants foram preservados.
4. O Edge reabriu as admissões. O fechamento canônico encerrou o processo do Pi. [Resultados e hashes](si041-native-admission-rollback.json)

A primeira montagem do roteiro usava um atributo incorreto para observar o link. O ensaio completo usou o estado `online` e um ambiente descartável novo. A entrega acrescenta evidências e dispensa migração. SI-T-I03 mantém aberta a campanha consentida com provedor real. O ensaio nativo usou o Connector na mesma máquina.
