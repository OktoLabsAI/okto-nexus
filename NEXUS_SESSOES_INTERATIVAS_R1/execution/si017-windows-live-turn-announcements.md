# SI-T-E14 · Avisos de fim de turno no Edge para Windows

O Edge 158.0.4370.33 apresentou os avisos da conversa em uma região acessível `status`, com `live=polite` e `atomic=true`. O teste abriu a sessão exata pela Home operacional e consultou a árvore de acessibilidade do navegador. Ele usou o Nexus 0.3.8 instalado em um ambiente virtual e o Windows 26H2. A API e o navegador trabalharam em loopback com uma cópia descartável do banco e eventos sintéticos. [Resultados e hashes](si017-windows-live-turn-announcements.json)

- Duas páginas carregaram sete resultados históricos sem anunciar finais antigos. Os 24 fragmentos novos apareceram na conversa sem avisos por fragmento.
- Dois finais distintos produziram `Turn finished.` e `Another turn finished.`. A repetição do mesmo resultado ficou em silêncio e a API a omitiu da projeção canônica.
- Dois finais na mesma página produziram um aviso `2 turns ended.`. Uma segunda página com dois finais novos produziu um aviso `2 more turns ended.`. O foco permaneceu em **Conversation messages** durante as atualizações.

A rodada final carregou explicitamente a segunda página do histórico antes de observar as atualizações ao vivo e usou um identificador de mensagem exclusivo para a nova rajada. As duas verificações terminaram com código zero. O banco passou na checagem de integridade, a fila de despacho recebeu zero operações do ensaio e o servidor e o navegador foram encerrados.

O NVDA 2026.3.1 portátil iniciou com perfil descartável em uma área de trabalho separada da área de entrada do Windows. O Edge abriu uma janela nessa área, mas o canal de controle do navegador não ficou pronto. A rodada no Edge verificou a árvore acessível e as atualizações da região de status. A fala com um leitor de tela do Windows segue pendente. A prova de fala com Orca e Chromium continua válida para aquela combinação. [NV Access](https://www.nvaccess.org/post/nvda-2026-3-1/) [Orca](si017-orca-live-turn-announcements.md)

Uma segunda montagem conseguiu controlar o Chromium 158.0.8127.18 por pipe com o NVDA na mesma área de trabalho privada. Uma página de controle exibiu o aviso na região acessível e preservou o foco do documento. O Windows manteve essa janela fora do primeiro plano, e o log de fala do NVDA registrou apenas a área de trabalho. O aviso positivo de controle ficou sem fala. A tentativa exercitou a montagem do teste e deixa a fala no Windows pendente. Os processos do teste foram encerrados e a área de entrada do usuário permaneceu a mesma. [Resultados e hashes](si017-windows-live-turn-announcements.json)

Este marco altera o registro de evidências. Dispensa migração, e o rollback consiste em reverter o commit do Nexus. O aceite do participante e as campanhas de provedor seguem pendentes. A medição adicional no macOS fica adiada para outro corte.

## Entrega à API de acessibilidade do Windows

No Chromium 158.0.8127.18 com o Nexus 0.3.8 instalado, um observador Win32 registrou `EVENT_OBJECT_LIVEREGIONCHANGED` no processo do navegador. O controle positivo confirmou a captura do evento antes da prova do Nexus. O navegador rodou em uma área de trabalho privada, enquanto a área de entrada do usuário permaneceu a mesma. [Eventos Win32](https://learn.microsoft.com/en-us/windows/win32/winauto/event-constants#event_object_liveregionchanged)

Os sete resultados anteriores abriram sem anúncio na região de término. A rajada de 24 fragmentos e a repetição de um final geraram zero eventos de região viva após a conversa abrir. Seis finais canônicos geraram quatro eventos no mesmo objeto acessível, um para cada final isolado e um para cada par agrupado. O texto mudou de **Turn finished.** para **Another turn finished.**, depois para **2 turns ended.** e **2 more turns ended.**. O observador registrou zero trocas de foco após a abertura da conversa.

O Chrome instalado falhou ao abrir na área privada durante o controle. O Chromium do ambiente de testes passou no controle e nas duas execuções do Nexus. A primeira execução completou os checkpoints, mas o redirecionamento do PowerShell devolveu código 1 ao receber uma mensagem diagnóstica. Na confirmação, a API e o observador encerraram com código zero, e a porta local foi fechada. O SQLite manteve a integridade e não houve despacho de operações ou chamadas a um provedor. [Comandos e hashes](si017-windows-live-turn-announcements.json)

A captura Win32 confirma a entrega dos eventos à camada de acessibilidade do Windows. A confirmação da fala pelo NVDA em primeiro plano continua pendente. Este marco registra evidências e pode ser revertido pelo commit.
