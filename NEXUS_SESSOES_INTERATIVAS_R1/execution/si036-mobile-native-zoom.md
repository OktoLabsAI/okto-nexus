# SI-034 e SI-036 · Fila e controles em 360 px com zoom de 200%

Testei o painel em 360 px no Chrome para Windows, primeiro com zoom padrão e depois em 200% selecionado nas configurações do navegador. O segundo ensaio manteve 360 pixels CSS. Medi os controles no navegador e confirmei que texto e botões cabiam no painel.

Com Tab e Enter, enfileirei uma mensagem, pausei e retomei a fila e abri a revisão de reorientação. Nas duas escalas, **Keep paused** devolveu o foco à fila. Cancelar a reorientação devolveu o foco ao botão que abriu a revisão. Os recibos da API confirmaram as mudanças, e a mesma mensagem permaneceu na fila enquanto o turno original estava ativo.

Ao liberar a resposta simulada, o Pi 0.87.1 recebeu a mensagem uma vez. Dois turnos terminaram com resultados canônicos e o fechamento da sessão encerrou o processo. Passaram 19 testes de componentes e três testes da API com o pacote instalado. O ensaio usou um provedor local sintético.

A captura padrão do Playwright recortou as imagens a 200%. As medidas dos controles foram obtidas diretamente no navegador. A captura completa de 720 pixels foi feita após o encerramento da aplicação de teste. O pytest encerrou com falha na desmontagem do servidor HTTP, depois das ações e do fechamento canônico do Pi. A porta temporária foi confirmada fechada. Uma tentativa de repetição parou antes de abrir o navegador.

O ledger registra SI-T-E13 como aprovado para o fluxo observado. O rollback é a reversão deste commit de evidências, sem migração. Dispositivo físico, leitor de tela e aceite humano continuam em aberto.

[Dados, medições e hashes](si036-mobile-native-zoom.json)
