# Startup automático do controle R4 — parcial M02/M06

O daemon agora consome o registro persistente de executor. Verifica o protocolo
público, recupera um bootstrap com a identidade escolhida, negocia HTTP/WSS,
consulta o journal Core e publica o inventário. Para esse Server não inicia o
transporte legado. A alteração de uma instalação com transporte legado vivo
exige drain explícito; reload não transfere ownership silenciosamente.

O schema 6 do Connector reserva a sequência de publicação antes do HTTP.
Perda de resposta, reconnect e reboot mantêm o executor canônico e avançam a
sequência. Após negociação, o produtor do inventário é o ID do canal reconciliado;
o boot ID local de processo continua separado. O ticket fica somente em memória.
Inventário é refrescado antes do fim do frescor informado pelo Server.

## Correção integrada no Nexus

A prova de reboot revelou que a recusa de novo produtor não tinha uma transição
de recuperação implementada. O Server agora vincula o bootstrap ao socket durante
o claim da geração. A publicação verifica novamente ticket, epoch, revisão,
revogação, expiry, executor e canal dentro da transação. Trocar produtor exige
CONTROL_READY, o mesmo canal do ticket e uma sequência estritamente maior.
Canal antigo, produtor divergente e revogação entre validação e commit falham.

O Connector negocia o canal antes da publicação quando R4 está qualificado.
Antes dessa qualificação, somente a publicação inicial de bootstrap é possível;
não anuncia runtime pronto. Conflitos/negações de inventário retornam erros HTTP
estruturados em inglês, com 409/403, em vez de escapar como falha de servidor.

## Provas executadas

| Campanha | Resultado |
|---|---|
| Connector completo | 325 passes; dois skips existentes |
| Connector dirigido | 65 passes |
| Nexus R4 completo | 107 passes |
| Handoff de inventário e regressões | Oito passes |
| Instalação isolada, fora dos clones | 109 passes |

Os grupos se sobrepõem. A jornada usa importação/registro pela CLI, daemon
run_forever, HTTP/WSS reais, IPC autenticado para status/shutdown e uma segunda
instância de daemon sobre o mesmo estado. Verifica zero operações e zero lanes:
controle pronto não significa execução pronta. O caso positivo fornece prontidão
sintética ao Server; o negativo usa as flags de produção inalteradas. Não é
campanha de provider, processos separados, Linux ou hosts independentes.

Manifesto e hashes: [test_runs_20260930_startup.json](test_runs_20260930_startup.json).
As tentativas com falha foram preservadas, incluindo a descoberta do bloqueio de
produtor no reboot. Credenciais geradas de laboratório foram redigidas nas cópias
de falha exportadas, com hashes registrados. Os módulos instalados foram comparados
byte a byte com os wheels e com os arquivos de produção após os testes.

## Trabalho restante

A reconciliação inicial prova apenas um namespace vazio. Claims, reservas nos
dois ledgers, IDs pendentes do Server, falha de leitura ou scan incompleto mantêm
a recuperação pendente. Não se infere ausência de recursos da ausência de runtimes
em memória. A recuperação não vazia/paginada ainda precisa ser implementada.

Faltam conectar automaticamente lanes e consumidores de execução ao ambiente e
capability aprovados, renovar tickets de lane e leases, refrescar revisões do
binding e recuperar receipts/eventos duráveis. O ciclo local, governança completa,
UI/CLI, auditoria US English, migração/rollback e matriz provider/SO continuam no
plano. O schema 6 é recusado pelos binários antigos; o ensaio completo de rollback
permanece M12. Nenhuma flag de prontidão nem gate G0–G3 foi promovido.

A revisão final também recusa watermarks/cursors solicitados no handshake.
Depois desse ajuste, o Connector foi reempacotado e as campanhas dirigida,
completa do Connector e instalada coordenada foram repetidas.
