# Recuperação da resposta da checagem de versão

A campanha M1 v8 parou antes de setup:test: a observação da versão já estava
persistida e publicada quando a CLI perdeu a resposta do POST. A fronteira de
30 segundos é sustentada por horários e fonte; não há trace interno desse await.

O cliente agora observa a mesma seleção por GET após OUTCOME_UNKNOWN com efeito
possível, sem repetir POST nem comando de versão. Exige Server/executor/candidato/
adapter exatos, inventário fresco e autoridade atual. O prazo é verificado entre
consultas e após gravações antes do próximo efeito. Recusas definitivas permanecem
recusas; falhas de leitura preservam a incerteza do check submetido.

Os bytes finais passaram em59 casos instalados:34 no fluxo de conexão e25 nos
contratos adjacentes. Os982 payloads dos três wheels foram conferidos antes/depois,
com imports exclusivos no novo prefixo e entradas de teste inalteradas. As rodadas
fonte26/33 são intermediárias; apenas o novo caso final foi repetido na fonte.

O timeout de cada HTTP continua limitado separadamente; não há promessa de
cancelamento rígido. Um test_submitted salvo antes de expirar o prazo permanece
conservador se o POST não começou, sem replay automático. Nenhum provedor real,
serviço Windows ou campanha foi reexecutado. M1 e demais aceites reais continuam
pendentes. A v8 permanece encerrada com fault/reserva preservados.
