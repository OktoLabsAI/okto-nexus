# SI-013 e SI-036 · Envio quando a sessão está ociosa ou ocupada

O botão mostra **Send** quando o Nexus confirma que a sessão gerenciada está ociosa e **Add to next turn** durante um turno confirmado da mesma sessão e geração. Quando falta evidência, aparece **Send for next turn**. Clique e Enter usam o caminho canônico da fila, com a decisão de admissão no servidor.

No teste da API, o harness simulado começou sem eventos e o servidor devolveu estado desconhecido. Depois da confirmação do stream, a sessão apareceu ociosa. Com o início do turno, o servidor registrou estado ocupado e a revisão de envio continuou válida. A API aceitou a mensagem preparada enquanto a sessão estava ociosa e manteve o item na fila enquanto o turno ocupava a sessão.

No navegador com o pacote instalado, um processo Pi 0.87.1 executou o primeiro turno com a resposta de teste retida. Digitei um rascunho com **Add to next turn** visível. O fim do turno mudou o botão para **Send** no mesmo painel e preservou texto e foco. Um clique recebeu HTTP 202 com o estado **Queued** e produziu exatamente um novo turno no mesmo processo. Os dois resultados foram gravados e o fechamento canônico encerrou o Pi.

Passaram 420 testes frontend, dois de API no código-fonte, quatro de API com o pacote instalado e um ensaio no navegador com Pi real. O ensaio usou um provedor sintético. O Ruff reproduziu três ocorrências de ordenação de imports já presentes no baseline. Ensaios com provedor externo, leitor de tela e usuário seguem pendentes.

A alteração dispensa migração. Para reverter, reverta o commit do Nexus. A próxima etapa é verificar as ações e o foco no viewport móvel e com zoom de 200%.

[Dados e hashes dos ensaios](si013-next-turn-label.json)
