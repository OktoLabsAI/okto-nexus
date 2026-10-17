# M4d2 — Manutenção histórica independente da prontidão

## Mudança

Depois de comprovar contenção de recursos, continuidade dos eventos e resolução
das entregas, a recuperação pode publicar READY sem aguardar a gravação dos
certificados de retirement das sessões antigas. Um trabalhador retido por agente
faz essa manutenção em páginas de uma sessão. O cursor avança inclusive quando
uma sessão falha e volta ao início; a pendência canônica permanece no SQL até a
prova e o commit. Não há descarte, repetição de efeito nativo ou liberação por
timeout. Shutdown aguarda esse trabalhador, sem tratar cancelamento como prova.

A manutenção também foi retirada do trabalhador que publica respostas atuais.
Separar apenas a transição READY continuaria permitindo que um histórico lento
retivesse as novas respostas do mesmo agente.

Na revisão de M3f, a tolerância a DB_ERROR transitório foi restringida ao aviso
RECOVERY_PUBLICATION_DELAYED. Os demais registros de recuperação continuam
obrigatórios, inclusive os usados antes de liberar recursos.

## Validação

A campanha inicial de fonte teve 35 aprovações e uma falha: um teste existente
esperava que o certificado histórico já estivesse salvo no instante de READY.
Ele agora aguarda separadamente o certificado, mantendo a exigência de
invalidação quando há reserva ocupada. Os 24 testes de retirement passaram
na repetição. A campanha instalada é registrada em `m4d2-results.json`.

Os novos cenários mantêm a manutenção histórica bloqueada após um restart e
exigem resposta final de uma nova chamada do mesmo agente, nos adaptadores Pi,
Claude e Codex. Também verificam trabalhador único, retomada justa após erro,
ausência de certificados inventados e espera do trabalho retido no shutdown.
Os peers desses testes são determinísticos, não provedores reais.

## Limites

Esta mudança não conclui M4: a primeira auditoria de arquivos, a primeira
reconciliação obrigatória e os limites de varredura ainda precisam evoluir.
Não implementa substituição automática de um owner já contido (M6).

O teste real feito pela interface em 17/10 usa a instalação M3f, anterior a
M4d2: Pi respondeu M3F_PI_OK e Claude respondeu M3F_CLAUDE_OK, ambos com 1/1 ACK.
Não se usa essa evidência para afirmar que a latência real de M4d2 foi qualificada.
Codex não recebeu nova chamada porque há uma pendência externa de quota (L5).

## Achados da observação real

- Agents mostrou RECOVERING antigo até Refresh Agents. O backend já estava
  READY para os três. A tela possui polling que pausa quando document.hidden;
  ainda não se atribuiu a causa do atraso a esse mecanismo. Registrar como
  observação, sem alegar correção de frontend.
- As quatro reservas de aquecimento do Pi ficaram STARTING com sessões
  FAILED/NONE. As aberturas possuem recusa durável RESOLVED_TERMINAL,
  stage=dispatch, possible_effect=false, código CONFLICT e nenhum recibo Core.
  A mensagem coincide com a recusa de `execution_dispatch.py` para inventário
  que perdeu a validade antes do despacho (`The dispatch inventory is no longer fresh.`).
  A manutenção do pool reconhece FAILED/CLOSED ou recibo Core sem efeito, mas
  não essa recusa anterior ao Core. A chamada real conseguiu responder usando
  a quinta vaga sob demanda. A correção deve consumir prova de não envio
  estrita, nunca considerar FAILED/NONE isoladamente como liberação segura.
