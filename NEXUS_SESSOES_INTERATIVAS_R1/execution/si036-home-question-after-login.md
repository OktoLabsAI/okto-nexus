# SI-036 Retorno à pergunta após entrar como operador

O login recria o dashboard para descartar o estado associado à identidade anterior. A Home conserva em memória apenas a referência selecionada e tenta reabri-la uma vez, no mesmo servidor e projeto. Depois do login, consulta a ocorrência exata e usa a autorização atual para habilitar a ação. Encerrar a inspeção, sair da conta ou perder a autorização limpa a referência.

Em uma wheel instalada em diretório temporário, o Edge abriu uma pergunta do Pi na Home e entrou como operador pelo formulário do painel. O navegador consultou a ocorrência pelo seu identificador e pelo projeto original. A mesma pergunta reapareceu sem reabrir o painel. Antes de o operador escolher a resposta, houve zero envios de decisão. O sino permitiu responder às duas perguntas seguintes e voltou a zero. O Pi recebeu as três decisões, com três recibos `SUBMITTED` e apenas um processo escritor. A mesma sessão permaneceu acessível pelos visualizadores até o encerramento canônico.

Os testes de API confirmaram leitura sem alteração de estado, recusa a outra credencial e ao projeto errado, ausência de substituição para um identificador inexistente e inspeção sem ação de resposta após expiração. O ensaio no navegador usou Pi 0.87.1 real no Windows, diálogos de extensão descartável e respostas determinísticas. Houve zero chamadas a provedores.

A mudança é restrita ao Nexus, dispensa migração e pode ser revertida pelo commit que contém o endpoint, o painel e o bundle. O ensaio cobre a aprovação em navegador real para este fluxo. O gate completo de SI-036 ainda inclui teclado, zoom, leitor de tela e aceite humano. [Dados do ensaio](si036-home-question-after-login.json)
