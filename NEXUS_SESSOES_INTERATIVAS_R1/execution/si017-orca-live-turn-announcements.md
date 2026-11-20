# SI-T-E14 · Avisos de fim de turno no Orca

No pacote anterior, dois turnos distintos exibiam `Turn finished.` na região de status. O Chromium entregou o primeiro aviso ao Orca. Na segunda atualização, trocar o elemento pelo mesmo texto não produziu fala. A correção varia a frase quando o próximo aviso teria o mesmo texto do anterior. O agrupamento continua seguindo a página da conversa verificada pela API.

O ensaio usou o wheel instalado em Debian 13 sob WSL2, Chromium 156 com janela em Xvfb e Orca 48.1. O Orca recebeu eventos via AT-SPI e usou o Speech Dispatcher com eSpeak NG. O áudio foi gravado em uma saída virtual e conferido junto ao texto enviado ao sintetizador. O contêiner rodou sem rede externa. A API usou uma cópia descartável de histórico com eventos sintéticos e sem permissão para iniciar trabalho. [Versões, hashes e observações](si017-orca-live-turn-announcements.json)

- O foco permaneceu em **Conversation messages** durante as transições. O histórico abriu sem aviso de fim de turno e a rajada de 24 fragmentos ficou em silêncio.
- Os dois primeiros turnos distintos geraram `Turn finished.` e `Another turn finished.`. A repetição do mesmo resultado entre eles ficou em silêncio.
- Dois finais na mesma página geraram `2 turns ended.` uma vez. Uma segunda página com dois finais distintos gerou `2 more turns ended.` uma vez.

Passaram 422 testes do frontend, 24 testes de transcrição no código-fonte e os mesmos 24 no pacote instalado. O build do dashboard e a validação do wheel e do sdist também passaram. As primeiras rodadas ajustaram dependências da área gráfica, o socket de fala e a fixture de resultados. A rodada final encerrou o servidor e removeu o contêiner. O rollback consiste em reverter este commit do Nexus e dispensa migração. A verificação cobre a combinação Orca e Chromium descrita. O aceite humano e os ensaios com leitores de tela do Windows seguem pendentes.
