# M6d — Connector separado com pipe nomeado e Pi real pela interface

Data: 2026-10-17/18 (America/Sao_Paulo / UTC). Checkpoint parcial de M6; não é decisão de adoção nem conclusão de UI-B/UI-C.

## Artefatos e isolamento

- Nexus 0.3.1 instalado de wheel SHA-256 `b98b88e9f37bb2e16e48cc7a3a7c65532826b5385bb12da263ae0ec40ee50062` em `build/m6d-env`.
- Core 0.0.12 vendorizado nos dois repositórios, wheel SHA-256 `55b58a13f7112e63a44a08efb787ca5e43128f4d090fd639a7a9b307e5e43ecd`.
- Connector 0.0.10 instalado do wheel M6c, SHA-256 `beb7302c34049de36dcd36a06a508fcb3b05c2d7a27149f70e3a68e7dd55d8e6`, com transporte experimental `named_pipe`.
- Home/workspace exclusivos em `build/runtime-m6d-ui`; Nexus escutou apenas `127.0.0.1:8204`. Estado exclusivo do Connector em `AppData/Local/okto-nexus-connector-m6d-20261017`. Nada foi alterado na instalação global.
- Nexus: PID 18016 antes, 45008 depois do reinício. Connector: PID 19076 inalterado durante o teste. Pi 0.87.1 configurado como agente remoto `m6d-pi`, sessão `per_sender`, via UI de Agents/Connections, com registro e aprovação R4 pela UI. O primeiro registro precisou parar e iniciar o daemon experimental uma vez para sair do conflito de ativação R4; a solicitação durável foi retomada pelo mesmo request ID e aprovada. Essa intervenção foi parte da configuração inicial, não da recuperação medida abaixo.

## Execução real pela UI

O Meta-harness enviou três mensagens privadas no workspace M6D; o terminal de sessões e a conversa foram observados no navegador real. Em todos os três casos houve resposta exata e ACK 1/1:

| Cenário | Sessão | Admissão UI | Harness pronto | Resposta/turno concluído | Resultado |
| --- | --- | --- | --- | --- | --- |
| Referência antes do reinício | `ses_0f9d6dec49f7b7940cbae86cc888a530` | 00:25:33 UTC | 00:27:09 | 00:27:17 | `M6D_BASELINE_OK` |
| Depois do reinício do Nexus | `ses_0bbc3b316b2e66d9274bc44564f25c63` | 00:29:59 | 00:31:45 | 00:31:51 | `M6D_AFTER_RESTART_OK` |
| Depois de falha controlada do owner | mesma sessão `ses_0bbc…25c63` | 00:33:00 | já pronta | 00:33:07 | `M6D_AFTER_OWNER_RECOVERY_OK` |

A primeira abertura levou cerca de 96 s até `Harness ready` e 104 s até resposta. A segunda levou cerca de 106 s até pronta e 112 s até resposta. Esses tempos foram vistos no terminal; ainda falta decompor a etapa de abertura e medir uma distribuição. A terceira chamada reutilizou a sessão Pi aberta no Connector e concluiu em cerca de 7 s. Os números são três amostras, sem controle de carga, e não demonstram o comportamento de um pool one-shot.

## Reinício e contenção

O Nexus recebeu parada normal às 00:28:19.646 UTC. Seu coordenador registrou `DRAINED`, sem recursos ou códigos de erro, às 00:28:21.179; o lifespan terminou às 00:28:21.997. O novo processo iniciou às 00:28:33.075 e ficou pronto às 00:28:35.948 com o mesmo home. O Connector permaneceu vivo. A consulta durante a transição mostrou `REGISTERING`/`EXECUTOR_OFFLINE`; em 00:28:46.761 ele voltou sozinho a `CONTROL_READY`, agente `CONNECTED`. Portanto, nesta amostra, o controle recuperou cerca de 10,8 s após o servidor ficar pronto e 24,8 s após o lifespan anterior terminar. A segunda mensagem foi enviada depois dessa reconexão; seu ACK e resposta confirmaram a entrega efetiva, não apenas o status.

Às 00:32:16.178, o fixture marcou uma falha controlada no owner embutido, sem parar o processo HTTP. A geração 3 drenou; a geração 4 apareceu às 00:32:17.072 e seu pump iniciou às 00:32:17.479. O PID do Nexus ficou 45008, o Connector permaneceu `CONTROL_READY`, e a chamada seguinte concluiu na mesma sessão remota. A observação não equivale a cortar o WebSocket de controle do Connector nem prova comportamento de trabalho em andamento no instante da falha.

Após o teste, o daemon foi parado por sua CLI autenticada. O Nexus drenou às 00:34:54.575 e finalizou o lifespan às 00:34:55.141. Os PIDs 18016, 19076 e 45008 terminaram; as portas de teste 8204 e 8428 ficaram sem listener. O navegador de teste foi fechado. Evidência bruta descartável: `build/runtime-m6d-ui/evidence.jsonl` e estado/registro locais sob as pastas exclusivas acima; não contêm a chave de agente no relatório.

## Limites e próximos gates

Este checkpoint confirma um fluxo real de configuração, autorização, entrega, reinício e substituição de owner com o Connector local separado. Não qualifica sessão one-shot aquecida, interrupção da conexão de controle com turno em andamento, expiração/revogação de lease, replay/ausência de efeito duplicado, reinício do host Connector, concorrência/carga, comparação justa com o host embutido, custo de memória completo ou outro sistema operacional. O snapshot isolado após as respostas foi 146,5 MiB de working set do Nexus e 102 MiB do Connector; não há baseline comparável nem total dos filhos Pi. M6 continua aberto, e a latência de abertura Pi permanece no trabalho M7/L22.
