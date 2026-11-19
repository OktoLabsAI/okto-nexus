# SI-020, SI-025 e SI-037 — Terminal do Pi com consumo lento

No wheel anterior, a saída para um terminal lento expirava, mas a apresentação continuava `ACTIVE` enquanto o fechamento do WebSocket estava bloqueado. O teste reproduziu o estado ativo depois de o renderer já ter sido liberado. Agora o Nexus encerra a apresentação no broker antes de tentar enviar o fechamento. O servidor espera até cinco segundos por um envio e até dois segundos pelo fechamento. [Regressão do transporte](../../tests/session_interaction/test_presentation_transport.py)

O renderer do Pi entrega uma tela recente ao reanexar. Para consultar conteúdo que ficou fora dessa tela, use a conversa ou os recibos da sessão. A correção está na rota de apresentações e preserva os protocolos instalados. O rollback pode reverter o commit pelo Git. [Guia do terminal](../../docs/terminal-work.md)

No ensaio com Pi 0.87.1 real e Nexus instalado a partir do wheel, o editor parou de ler o WebSocket. O ensaio reteve o envio e o fechamento no limite ASGI apenas para aquele socket. O Nexus liberou o editor e o próximo terminal ConPTY abriu a mesma sessão. O PID do Pi, o socket de controle do Connector e a concessão produtiva permaneceram os mesmos. A entrada enfileirada foi entregue uma vez, com o mesmo recibo recuperado depois da conclusão. [Pacotes e resultados](si037-pi-viewer-backpressure.json)

Enquanto os terminais estavam desanexados, o Pi produziu uma resposta de 50.425 bytes em um turno completo. Um novo terminal renderizou o fim da resposta. O histórico nativo registrou o prompt original e a entrada enfileirada uma vez cada. O encerramento canônico retornou `SUCCEEDED`. As respostas vieram do provedor simulado com rede externa desabilitada. Este ensaio cobriu um volume finito em loopback. Saturação de rede entre hosts, maior volume contínuo e outras plataformas ainda precisam de evidência.

Passaram os 47 testes de apresentação e transporte do Nexus em código-fonte e no wheel instalado, além de dois testes do renderer no wheel do Core. O primeiro ensaio nativo consultou o recibo antes da confirmação. O ensaio final verificou o mesmo identificador antes e depois de concluir a execução.
