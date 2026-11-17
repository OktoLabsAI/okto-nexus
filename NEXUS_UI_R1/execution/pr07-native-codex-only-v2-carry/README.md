# UI042 Codex A/B: continuação restrita com carry permanente

Este derivado preserva os candidatos anteriores e seus dados. A resposta real
`call_7b291505d2a349ddb591321ccaefe5f7 item0` autorizou somente Codex. O Root
autorizou preparar esta continuação após comprovar que a tentativa anterior parou
em GET runtime-options, antes de SetupTest. Não há nova pergunta ao usuário ou
consentimento transplantado. O Root audita este SHA e emite seu mapeamento
genuíno da autorização antes de executar.

O antecedente reservou um slot de75.000, que **não é devolvido**. Seus recibos
DRAINED/saída física e provas de zero operações, sessões, bindings, grants,
identidades de campanha e journals de Test estão pinados em carry.json.
connection_test_runs/connection_setup_views não existem neste schema; Tests são
em memória. Não inventamos contagens dessas tabelas. Traceback e ausência de
journals/commits comprovam o corte anterior ao Test. Preflight reconfere hashes,
settlement e contagens no DB antigo em modo somente leitura. Novo root é permitido
por essa prova de ausência de execução, sem replay de resultado desconhecido.

Máximo **cinco novos slots**: A.setup, B.setup, A.work, A.continue, B.work.
B.continue removido. Global:1histórico+5novos=6reservas; carry75k+5x75k=450k.
Máximo observado500k, gatilho preventivo450k, reserva50k. Débito novo é
max(75k,observado por admissão), mais carry permanente. Terminal/quiet timer não
devolve provisão. Se consumo maior ou desconhecido impedir os cinco, para sem
repetir. Este escopo parcial não qualifica a antiga jornada de seis turnos úteis.

Codex A/B têm agentes e sessões independentes, modelo exato gpt-5.3-codex,
adapter codex_app_server e mesmos bytes BXP qualificados. B recebe o workspace_id
canônico do Finish de A. A é comparado após B; continuar A preserva scope/epoch/
native identity. Sem fallback de conta/modelo/executável. Zero execução ou auth
Claude. Parser puro legado não concede permissão a outro formato.

Correção readiness: após query-ready e antes da primeira reserva/review,
consultar somente GETs canônicos me/executors/runtime-options, por até120s.
Exigir executor/candidato/adapter exatos, inventário revisionado, freshness FRESH
e can_configure. Versão deve coincidir com metadata passiva pinada, atualmente
None/desconhecida: não prova versão/login/modelo. Version check canônico continua
na review após reserva. Ausência/timeout encerra sem nova reserva ou Test.
runtime-options pode materializar metadados de revisão; não concede/consome grant,
abre vault ou invoca provedor. Não é promessa de DB byte-idêntico.

Uso observado soma deltas cumulativos por journal/sessão exatos, correlacionados
por operação/turno. Uso antigo não cobre operação nova. Path do journal coincide
com EmbeddedRuntimeHost instalado. reported_accounting_final=false: provisão não
é limite superior real ou cap de faturamento atômico. Retries/ferramentas internos
e uso atrasado podem ultrapassar o teto. Cinco admissões não garantem cinco HTTPs.

Após cinco pedidos: janela passiva Home até180s; somente public/observer.done com
campaign_id exato termina cedo. Ausência=NOT_RUN, sem novo turno. Falha anterior
vai direto ao cleanup. Trabalho CSV/JSON e continuação têm oráculo local; sem
pedido corretivo. Prompt semtools não garante ausência de atividade interna CLI.

Server/home/DB/projeto próprios; sem instalação pessoal, cópia de login, leitura
de auth na preparação, serviço Windows ou reinício de sessão. Após aprovação,
CLI pode usar e escrever naturalmente no provider_home declarado. Ambiente
herdado filtrado case-insensitive. Cleanup confere owner antes da parada normal
ou força canônica própria; complete exige DRAINED da geração e saída física.
Dados preservados. Não altera grants/leases para fabricar settlement.

qualification-final.json fornece argv e dry-run/preflight RO. Preparação não
executa v2.28 testes offline sintéticos não provam modelo disponível ou M3 real.
