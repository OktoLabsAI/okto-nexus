# SI-037 · Continuidade com um leitor lento no Windows

O ensaio rodou com Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16 instalados. O executor embutido do Nexus abriu o Pi 0.87.1 nativo, com resposta simulada, e serviu a apresentação por WSS em loopback. [Ambiente, pacotes e resultados](si037-current-windows-slow-reader.json)

1. O cliente que parou de ler provocou pressão de escrita no socket. Houve um envio cancelado e o gateway desanexou aquele leitor. Nessa configuração, o maior frame observado teve 12 KiB.
2. Antes de o turno terminar, um terminal ConPTY abriu a mesma sessão e acompanhou as atualizações seguintes. O Pi continuou no processo original. O leitor substituto exibiu o marcador final e saiu pelo controle de detach.
3. O resultado canônico reteve os 192.076 bytes da resposta, inclusive o prefixo que já havia saído da janela do terminal. O SQLite confirmou uma sessão, um turno, um resultado, dois leitores desanexados e um fechamento canônico. A integridade do banco e a saída do Pi foram confirmadas.

Passaram o ensaio WSS com o pacote instalado e 127 regressões de processo, observação de ownership e CLI. A execução no Windows pulou o caso que exige PTY POSIX. A SI-037 preserva as evidências próprias de fechamento de janela, perda do cliente, saída sem leitor, drenagem do Connector e PTY Linux. [Saída sem visualizador](si037-pi-headless-output.md) [Parada controlada do Connector](si037-controlled-connector-stop.md) [PTY Linux](si037-posix-pty-hangup.md)

Os valores descrevem esta execução na máquina compartilhada. A medição adicional no macOS e os testes que encerram a sessão do Windows continuam adiados. O marco atualiza o ledger e as evidências. A reversão do commit dispensa migração.
