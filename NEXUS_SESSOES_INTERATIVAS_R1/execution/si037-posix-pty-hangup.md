# SI-T-H07 — Fechamento de um terminal POSIX

O cliente Nexus instalado rodou em um PTY controlador de um contêiner Linux descartável sob WSL2. A apresentação Pi em leitura chegou por WSS ao Nexus e ao Pi 0.87.1 executados no Windows. Os pacotes do cliente e do host vieram dos mesmos wheels. O provedor era determinístico e local. [Resultados, versões e hashes](si037-posix-pty-hangup.json)

1. O Pi chegou ao turno autorizado e o terminal Linux exibiu o marcador do histórico. O Nexus admitiu uma entrada de próximo turno, sem iniciar uma segunda execução.
2. Fechar o master PTY fez o kernel entregar SIGHUP ao processo leitor. O broker desanexou o leitor. O mesmo processo Pi, o turno original, a concessão produtiva e o recibo enfileirado permaneceram ativos.
3. Depois da liberação da resposta simulada, o Nexus registrou os dois resultados sem visualizadores. O histórico nativo confirmou uma única entrega para cada texto. O fechamento canônico encerrou o Pi. A auditoria confirmou o SQLite íntegro, a chave TLS removida, o listener fechado e o contêiner removido.

Passaram a integração instalada e 19 regressões de broker e fila. A primeira rodada já havia observado SIGHUP no Linux, mas a fixture exigia `SUBMITTED` enquanto a API ainda reportava `ACCEPTED` para um turno que já estava em execução. A rodada concluída verificou a execução pela atividade nativa, pelo processo e pelos resultados. A qualificação cobre Linux como cliente e Windows como host do Pi. A reversão do commit dispensa migração.
