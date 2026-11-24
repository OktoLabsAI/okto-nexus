# SI-T-E14 · Avisos de fim de turno no Edge para Windows

O Edge 158.0.4370.33 apresentou os avisos da conversa em uma região acessível `status`, com `live=polite` e `atomic=true`. O teste abriu a sessão exata pela Home operacional e consultou a árvore de acessibilidade do navegador. Ele usou o Nexus 0.3.8 instalado em um ambiente virtual e o Windows 26H2. A API e o navegador trabalharam em loopback com uma cópia descartável do banco e eventos sintéticos. [Resultados e hashes](si017-windows-live-turn-announcements.json)

- Duas páginas carregaram sete resultados históricos sem anunciar finais antigos. Os 24 fragmentos novos apareceram na conversa sem avisos por fragmento.
- Dois finais distintos produziram `Turn finished.` e `Another turn finished.`. A repetição do mesmo resultado ficou em silêncio e a API a omitiu da projeção canônica.
- Dois finais na mesma página produziram um aviso `2 turns ended.`. Uma segunda página com dois finais novos produziu um aviso `2 more turns ended.`. O foco permaneceu em **Conversation messages** durante as atualizações.

A rodada final carregou explicitamente a segunda página do histórico antes de observar as atualizações ao vivo e usou um identificador de mensagem exclusivo para a nova rajada. As duas verificações terminaram com código zero. O banco passou na checagem de integridade, a fila de despacho recebeu zero operações do ensaio e o servidor e o navegador foram encerrados.

O NVDA 2026.3.1 portátil iniciou com perfil descartável em uma área de trabalho separada da área de entrada do Windows. O Edge abriu uma janela nessa área, mas o canal de controle do navegador não ficou pronto. A rodada no Edge verificou a árvore acessível e as atualizações da região de status. A fala com um leitor de tela do Windows segue pendente. A prova de fala com Orca e Chromium continua válida para aquela combinação. [NV Access](https://www.nvaccess.org/post/nvda-2026-3-1/) [Orca](si017-orca-live-turn-announcements.md)

Uma segunda montagem conseguiu controlar o Chromium 158.0.8127.18 por pipe com o NVDA na mesma área de trabalho privada. Uma página de controle exibiu o aviso na região acessível e preservou o foco do documento. O Windows manteve essa janela fora do primeiro plano, e o log de fala do NVDA registrou apenas a área de trabalho. O aviso positivo de controle ficou sem fala. A tentativa exercitou a montagem do teste e deixa a fala no Windows pendente. Os processos do teste foram encerrados e a área de entrada do usuário permaneceu a mesma. [Resultados e hashes](si017-windows-live-turn-announcements.json)

Este marco altera o registro de evidências. Dispensa migração, e o rollback consiste em reverter o commit do Nexus. O aceite do participante e as campanhas de provedor seguem pendentes. A medição adicional no macOS fica adiada para outro corte.
