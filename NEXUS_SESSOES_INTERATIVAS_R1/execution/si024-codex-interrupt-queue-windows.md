# Interrupção e retomada da fila do Codex no Windows

O primeiro ensaio com dois app-servers reais mostrou que, após a interrupção, o Nexus aceitava a retomada e a fila permanecia sem despachar. O adaptador Codex já havia observado o fim do turno, mas a ponte do Core devolvia estado desconhecido. O Core agora usa o estado observado quando o processo está vivo e corresponde à thread registrada. Sessões encerradas, threads divergentes e adaptadores sem essa evidência continuam sendo tratados como desconhecidos para fins de admissão.

## Cenários verificados

- **SI-T-C11 e SI-T-C12.** O Nexus gravou a pausa da fila antes de enviar `turn/interrupt` para o turno selecionado. O recibo inicial indicou que o resultado aguardava confirmação. O evento nativo confirmou a interrupção. O processo selecionado permaneceu vivo e a sessão irmã continuou executando.
- **SI-T-C13.** Em um segundo ensaio, o primeiro turno terminou normalmente e o seguinte começou na mesma thread. Dois pedidos com a revisão antiga retornaram HTTP 409. A fila manteve seu estado, e nenhum comando nativo de interrupção, recibo ou alteração de alvo foi criado.
- **SI-T-C15.** Depois da retomada explícita, duas entradas foram admitidas na ordem original com a mesma concessão e revisão. A revisão de interrupção do turno anterior recebeu HTTP 409 durante a primeira admissão da fila. Repetir a ação aceita produziu um único envio nativo de interrupção.
- **SI-T-C03.** O app-server real já havia confirmado a rejeição de uma revisão antiga enquanto outro turno executava. Em cenário separado no Edge, uma resposta HTTP 409 controlada preservou o conteúdo editável do rascunho e não enviou um novo turno.
- **SI-T-C14.** No Edge, com um peer simulado, a UI recuperou o recibo após a perda da resposta HTTP. A confirmação chegou pelo evento correlacionado. Fechar e reabrir o painel manteve a entrada na fila pausada, sem iniciar trabalho.

O ensaio nativo usou Codex app-server 0.157.0, Nexus instalado a partir de wheel e resposta SSE determinística em loopback, com dois processos nativos em projeto temporário. Os dois cenários de navegador usaram Edge headless com a aplicação instalada e respostas controladas. A etapa não usou provedores externos, credenciais de modelo ou avaliação humana. Passaram 52 testes do Core, 140 do Connector e 12 do Nexus instalado. [Hashes, escopo e resultados do ensaio](si024-codex-interrupt-queue-windows.json)

Os dois consumidores usam o mesmo wheel do Core 0.0.16. Não houve migração de dados. Uma reversão conjunta dos pins restaura o wheel anterior e também restaura a limitação observada na retomada da fila. A qualificação do Codex segue em andamento, incluindo a entrada pelo terminal nativo e os demais cenários previstos no ledger.
