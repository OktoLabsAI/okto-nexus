# SI-041 · Pausar novas mensagens sem parar a fila

Em **Settings → Runtime → Global runtime defaults**, a opção **Pause new session messages** bloqueia novas mensagens e novas reorientações com texto. O executor continua processando o que já foi aceito. Consultar recibos, cancelar entradas e controlar a fila existente continua disponível. A pausa é uma política global persistente e usa a revisão existente para recusar gravações concorrentes obsoletas.

A decisão ocorre na transação de admissão. Browser, CLI e visualizadores nativos compartilham essa verificação. Repetir o mesmo envio recupera a entrada anterior. A pausa mantém a revisão da capacidade, o lease e a autorização do executor, de modo que mensagens admitidas podem avançar na fila.

No Edge automatizado, o bundle do wheel exibiu a opção e confirmou as duas gravações. O banco registrou a pausa na revisão 2 e a reabertura na revisão 3. Foi preciso fechar as telas iniciais de onboarding e métricas antes de abrir Settings. A verificação de navegador cobriu o controle global. Os testes de fila separadamente usaram o Core e R4 instalados com um peer nativo sintético.

O teste de fila recusou um envio novo, devolveu o mesmo recibo para uma repetição e despachou duas entradas retidas em ordem, no mesmo executor. Ao reabrir as admissões, aceitou uma mensagem nova com outro ID. Passaram 29 regressões instaladas e os 422 testes de frontend. [Resultados e hashes](si041-live-admission-pause.json)

A migração 190 foi aplicada em uma cópia do schema 189. Preservou as 98 linhas existentes, os quatro hashes de recibo e duas entradas nas condições `DELIVERY_UNKNOWN` e `BLOCKED_SESSION`. O wheel anterior recusou o schema atualizado e leu a cópia anterior. Para reverter só a interface, use a política global no banco atual. Um rollback de binário requer cópia compatível, com o runtime parado e os efeitos já reconciliados.

SI-T-I03 mantém aberta a campanha com provedor e a combinação do controle global com trabalho nativo em andamento. A verificação preserva a evidência anterior da troca de Home com um Connector e Pi ativos.
