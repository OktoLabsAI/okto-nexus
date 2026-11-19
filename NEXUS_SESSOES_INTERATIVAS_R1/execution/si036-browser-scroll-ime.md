# SI-013, SI-017 e SI-036 · Histórico e composição de texto

No Edge 157 em Windows, abri uma sessão Pi com 40 linhas de histórico e um turno em andamento. Posicionei o painel em um trecho anterior antes de liberar a resposta. Quando a mensagem apareceu, a altura do histórico aumentou de 864 para 936 px. A posição ficou em 100 px e a primeira linha visível permaneceu no mesmo lugar. O foco ficou no histórico e surgiu um único aviso de novas mensagens. Acionei o aviso com Enter e o painel foi até a resposta, com o foco de volta no histórico.

O navegador recebeu eventos de composição pelo protocolo DevTools do Chromium. Enter durante a composição e Enter no rascunho `/status` não dispararam chamadas de ação. Shift+Enter inseriu uma linha. Depois da composição, um Enter comum enviou exatamente o texto final em duas linhas. A API respondeu HTTP 202 e o Pi registrou a entrada uma vez, como mensagem de usuário na sessão original. Os dois turnos concluíram e o fechamento canônico foi confirmado.

Passaram 30 testes do frontend, 34 testes de conversa, stream e fila e o ensaio no navegador com o Pi 0.87.1 real. O Pi usou um provedor simulado sem saída para a rede. A rolagem foi comprovada para uma nova mensagem retida pelo Pi. A chegada de deltas de texto ainda precisa de evidência no navegador. O ensaio de composição usou o navegador real com entrada pelo protocolo, e a interação com um seletor de candidatos do sistema operacional segue fora deste ensaio.

Esta etapa atualiza o ledger e as evidências. O rollback é a reversão do commit de evidência e dispensa migração.

[Registro de evidências e hashes](si036-browser-scroll-ime.json)
