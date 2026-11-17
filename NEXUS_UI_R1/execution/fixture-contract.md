# UI-005 — contrato de fixtures de PR-00

Estado: **UI-005 implementada como fixture de PR-00; sete focais executados**.
UI-003/UI-004 tiveram freeze técnico aceito. Os cenários de produto continuam
dependendo da implementação e da execução de suas próprias jornadas.

## Implementação e execução atual — 2026-11-16

`fixtures.py::scenario(directory, recipient="operator"|"subject", clock=...)`
é um context manager reutilizável por pytest e por um futuro servidor de browser.
Exige diretório explícito vazio, usa `bootstrap({})`, descoberta local vazia,
relógio ISO/epoch consistente injetado antes do bootstrap, TestClient/WSS reais
e teardown de canal/lifespan/factory. Não executa o arquivo nativo sintético.
`ReadBarrier` fornece rendezvous por Event com timeout finito, sem sleeps.

Os IDs canônicos opacos são capturados do retorno da admissão; não são fixados
por UUID artificial. Há uma única `execution_installation` e todos os registros
de execução compartilham seu Server/executor reais. O alias A é `subject`; B/C
são identidades próprias da mesma instalação. Não há produtor global novo nem
cópia/mescla de bancos.

| Fato de fixture executado | Verificação focal |
| --- | --- |
| Duas conexões | Dois endpoints/bindings persistidos distintos, criados antes da admissão; `ConnectionFact` é modelo de teste, não DTO futuro nem alegação de prontidão. |
| Duas sessões do mesmo agente | Exatamente duas rows, contexto Server/executor/binding/workspace/workspace_binding/agent conferido por join. Uma READY admitida, outra CLOSED histórica sintética; IDs exatos diferentes. |
| A→B→C | Messages/deliveries e handoffs diretos persistidos; nenhum envio do operador; não se infere parentesco novo. |
| Trabalho sem executor | Handoff OPEN broadcast sem runtime_handoff_binding; a Home atual mantém runtime_refs vazio. |
| Pergunta ao operador | Variante input com admissão, grant, ticket/revisions atualizados, lease aplicado e event ingress canônicos; Home mostra awaiting_operator no session_id exato. |
| Pergunta ao agente | Variante independente agent_input mostra awaiting_agent; listagem HTTP visível apenas ao destinatário real e POST dos demais recebe403 em ambas as variantes. Não se responde à pergunta durante o teste. |
| Resultado incerto | Receipt OUTCOME_UNKNOWN, possible_effect=1, retry_safe=0, operação presente na Home; nenhum retry executado. |
| Sucesso e cleanup | Receipt SUCCEEDED e containment REQUESTED na sessão histórica; Home atual mantém cleanup_state=pending. |
| Externo | create_source/create_instance/issue_token/publish reais, fonte/instância retornadas encontradas na Home; token efêmero não publicado. |
| Fonte parcial | Falha sqlite3.OperationalError somente nos ports overview/work; work unavailable/total desconhecido, resultados e externo ready; leitura normal restaurada após o contexto. |
| Multiplicidade/páginas | Work atual state=all percorrido em páginas de1 até fim, conjunto igual à página completa e sem IDs repetidos. Isso não certifica o agrupamento/paging futuro de UI-003. |

Dados históricos adicionais são explicitamente `synthetic-read-fact`; não têm
admissão/lease próprios e não provam capacidade de retomar/autorizar conexão ou
executar essas operações. Perguntas operador/agente usam dois cenários próprios,
não uma fusão de authorities nem perguntas simultâneas artificialmente copiadas.
Seletores, grupos/children/session refs e navegação UI-003/UI-004 ainda não são
testados aqui. `ConnectionFact` fica separado desses DTOs ainda inexistentes.

Execuções:

- `rtk proxy .venv\Scripts\python.exe -m pytest tests/ui_simplification/test_fixtures.py -q -k "not single_current_baseline_sample"`: **6 PASS**,1 deselected,21.10s (tool `3b353e`, processo terminal0).
- `rtk proxy .venv\Scripts\python.exe -m pytest tests/ui_simplification/test_fixtures.py::test_single_current_baseline_sample -q -s`: **1 PASS**,5.67s (tool `6efe1f`, terminal0).
- `rtk proxy ruff check NEXUS_UI_R1/execution/fixtures.py tests/ui_simplification/test_fixtures.py`: PASS (`e5c524`).

Baseline controlado atual, **uma amostra final**, sem medição de latência:
`current_home_overview`,1 UoW read-only no thread chamador,54 statements SQLite
por trace (inclui nested reads),0 alterações nesse UoW,10.510 bytes JSON compacto
UTF-8 e5 seções ready. Não mede cliques/navegação, performance HTTP ou paginação
futura. Instrumentação preliminar capturou manutenção concorrente do lifespan e
falhou com6 UoWs; foi descartada, e a coleta final isola o thread da leitura.
As demais falhas de desenvolvimento (unicidade de endpoint, ticket antigo,
grant duplicado, assert de DTO e segundo lifespan indevido) foram corrigidas no
fixture/teste, sem alteração de produto. Nenhuma prova preliminar foi promovida.

Origens: Python `.venv/Scripts/python.exe`, Nexus `src/okto_nexus/__init__.py`,
Core `.venv/Lib/site-packages/nexus_connector_core/__init__.py`. O recorte não
importa CLI/service_manager e não qualifica instalação/distribuição do Core.
HEAD de partida `9de55d950739ed5d7348e946506e4c05464ccb13`.
SHA256: fixture `843bfcdcf89849ddb2dc1354dc6a977f9c422d6816cdbf0afe629b8c6d302eb7`;
teste `64d07ce070b7ee62ba180cac816005c7f736151a3b9d4c408b368706c2657814`;
UI-003 `c25b7fabf8de6a354b27d71e3913a6b0ac43994e75b2cc6c8d9e9de129a638ed`;
UI-004 `7ef403658d2b53d6106bdaba2c1e24bee2fe82039511f25012652a35aa717349`.

Todos os contextos/processos de teste terminaram; os diretórios pytest são
artefatos temporários do runner. Não ficou serviço/listener/provider iniciado
por esta tarefa. Nenhum ledger, produto ou instalação pessoal foi alterado;
nenhum commit/push foi feito por este agente.
T-BASE-04 tem fixture executável; T-DATA-10/T-QUAL-01 de produto não são PASS
por estes sete focais. Não há baseline de browser fabricado.

## Histórico da preparação e protocolo para as etapas seguintes

O texto a seguir registra a preparação anterior ao freeze e o protocolo que
orientou a implementação; suas dependências futuras não substituem o retrato
executado acima.

Este arquivo não qualifica cenários UI-R1 e não altera os ledgers anteriores.
O aceite exige fixtures compartilháveis e determinísticas, não um inventário
de cartões montado em React. O checkout observado está em `feature/v0.3.5`,
HEAD `9de55d950739ed5d7348e946506e4c05464ccb13`; preserva a Home anterior.

Foram lidos RTK, CONTRIBUTING, CI, UI-003/004/005 e T-BASE-04/T-DATA-10/T-QUAL-01.
Todos os comandos desta preparação foram leituras com prefixo `rtk`. Não houve
serviço, navegador, modelo, instalação, credencial pessoal ou fixture executada.

## Interface compartilhável proposta

`NEXUS_UI_R1/execution/fixtures.py` deverá fornecer um context manager de cenário
que receba um diretório temporário explícito e o relógio controlado. Nenhum
default pode resolver a instalação pessoal, o diretório corrente como projeto
real, perfis do usuário ou `os.environ` como configuração de autoridade.

O objeto de cenário expõe factory/config/clock/repos, serviços canônicos de
leitura e um mapa de aliases para os IDs reais criados no próprio cenário.
Aliases como `planner`, `reviewer`, `connection_a` e `session_a_2` são somente
endereços de teste; não são grupos de UI ou IDs substitutos enviados à API.
IDs opacos gerados canonicamente são capturados uma vez e reutilizados nas
asserções. Relacionamentos, sequência de eventos, relógio e desempates são
controlados; não se exige nem se fabrica um token de autenticação previsível.

A mesma criação de dados será usada por pytest e pela fixture HTTP/browser.
O browser recebe o app real sobre o mesmo SQLite, nunca primeiras páginas
concatenadas ou respostas JSON inventadas para simular inventário completo.
Asserts de autoridade usam os serviços reais; o fixture não define `can_submit`,
`can_answer` ou `can_resume` como booleanos pré-fabricados.

## Casos e fontes reutilizáveis

| Alias/caso | Fonte real a reutilizar | Fato/assert esperado na fixture |
| --- | --- | --- |
| Duas conexões no mesmo projeto | `application/terminal_connection.py`, `adapters/inbound/cli/terminal_target.py`, configuração de binding/endpoint/workspace existente | Dois registros persistidos distintos, com Server/instância/operador/projeto e binding coerentes; nenhum perfil pessoal nem criação de serviço. Identidade do registro segue UI-004 final. |
| Duas sessões da mesma identidade | `test_home_semantics.py::test_same_agent_two_sessions_keep_running_and_operator_wait_separate`; tabelas de operações/sessões/receipts | Sessões exatas distintas e estado por sessão; uma não pode virar a sessão mais recente da outra. Sessão sem operação não recebe operation_id fictício. |
| Cooperação A→B→C | `tests/home_evolution/fixtures.py::seed_scenario`, `test_home_queries.py::test_direct_delegation_keeps_each_handoff_and_canonical_task_title` | Remetentes/destinatários e atividades lógicas distintos, sem mensagem obrigatória do operador. Pai só quando existe referência persistida verificável; não inferir parentesco por título ou por agente. |
| Trabalho sem executor | Handoffs OPEN da mesma fixture migrada | Handoff válido sem sessão/binding/host inventados, ainda alcançável no conjunto completo. |
| Pergunta ao operador | `tests/execution_r4/test_native_decisions.py::decision_state` com `input`/`form` | Admissão, lease aplicado e ingress nativo canônicos; destinatário/operator e opções/tipos preservados. Fixture não decide nem concede autoridade por leitura. |
| Pergunta a outro agente | Mesmo helper com `agent_input`; `test_home_native.py` | Operador acompanha, mas não é destinatário de resposta; API real recusa personificação. |
| Resultado incerto | Operação/receipt sintéticos válidos e asserções de `test_home_queries.py`/`test_home_semantics.py` | Incerteza e possible_effect mantidos, sem retry ou nova operação decorrente da leitura. |
| Sucesso com cleanup pendente | `fixtures.py::_execution_cleanup` e `test_successful_turn_never_completes_or_verifies_handoff` | Resultado SUCCEEDED distinto da obrigação de cleanup, sem concluir/verificar handoff automaticamente. |
| Observação externa | `ObservationService.create_source/create_instance/issue_token/publish`, usados em `seed_scenario` | Fonte/instância/geração/workspace explícitos, prazo controlado e sem equivalência nativa inferida por nome/PID/agent_id. Tokens são efêmeros do teste e não vão para evidência pública. |
| Fonte parcial | Fronteira de query/service do teste `test_disabled_external_and_failed_work_are_not_empty_success` | Falha injetada no port de leitura; as demais fontes continuam reais. Total desconhecido não vira zero, partial não vira onboarding. Uma recusa de autorização deve continuar fatal para os dados protegidos. |
| Multiplicidade/paginação | `test_home_final_scope.py::test_all_projects_is_exact_paged_union_despite_repeated_memberships_and_links` e testes de namespace | Memberships repetidos, receipts/retries e relações de entrega extras não duplicam atividade; percorrer todas as páginas com desempate determinístico. |

Os paths de aplicação na tabela são relativos a `src/okto_nexus/`; paths de
testes sem prefixo explícito são relativos a `tests/home_evolution/`.

## Autoridade e composição dos dados

Os seeds HOME de leitura e os helpers de decisões nativas não podem ser unidos
copiando seus bancos ou IDs arbitrariamente. O seed HOME usa `fixture-server`,
enquanto o setup canônico cria sua própria instalação/executor e guarda revisions,
grants, scope e lease correspondentes. Para a fixture UI compartilhada, todos
esses vínculos devem pertencer à **mesma instalação temporária**. Reutilizar
construtores/helpers parciais e os IDs retornados; não inserir um segundo
`execution_installation` nem misturar grants de outra factory.

Fatos sintéticos só de leitura são identificados como tal. Não bastam para provar
que uma ação nativa é autorizada. Casos que exercitam uma decisão precisam da
cadeia canônica real usada por `decision_state`, sem executar Codex/Claude/Pi.
Uma chave efêmera emitida pelo próprio app de teste pode ser usada em testes de
HTTP; nunca se lê/copia autenticação pessoal nem se grava seu valor na curadoria.

O helper `bootstrap` atual constrói SystemClock internamente. A implementação
deverá injetar/substituir esse clock **antes do bootstrap** no escopo de teste,
ou construir explicitamente os serviços com o clock compartilhado. Trocar apenas
`deps.clock` depois de criar os serviços não fixa as referências já capturadas.
O relógio fixo deve ter ISO e epoch consistentes, como exige `iso_plus`.

## Relógio, barreiras e ciclo de vida

- Usar instante UTC fixo e avanço explícito, sem sleeps para validade lógica.
- Para GET atrasado, decisão concorrente e publicação entre snapshot/assinatura,
  usar barriers/events/futures observáveis; não atrasos probabilísticos.
- Eventos recebem sequência e timestamps ordenados; empates têm IDs explícitos.
- Os peers de protocolo, quando necessários, são sintéticos e contidos no teste.
  Se houver WebSocket vivo por mais tempo, manter heartbeat pelo protocolo real;
  não atualizar manualmente flags de liveness para simular autoridade.
- Não chamar descoberta de instalações pessoais, `--version`, setup produtivo,
  host service manager ou provider. App HTTP de demonstração usa lifespan off
  quando não precisa do canal canônico de controle.
- Fechar TestClient/peers/readers/factory antes de remover dados temporários.
  Um timeout não comprova saída física e não autoriza reiniciar a mesma fixture.

## Baseline a executar após UI-003/UI-004

1. Registrar SHA dos contratos, fonte e fixture antes da rodada.
2. Medir o contrato de leitura atual com o mesmo dataset: um UoW, SQL statements,
   writes recusados/zero e bytes do payload. Capturar a composição atual da Home
   como baseline, sem promovê-la à futura região única.
3. No modelo de UI-003, percorrer grupos e filhos com cursores até o fim;
   comparar o conjunto canônico de IDs distintos, não só a primeira página.
4. Registrar caminho de navegação/cliques para abrir cada sessão exata e voltar;
   testes Node/SQLite não substituem essa prova de browser.
5. Exercitar as duas conexões pelos seletores de UI-004, distinguindo retomar
   conexão, continuar sessão, nova sessão e recuperar envio incerto.
6. Executar T-BASE-04/T-DATA-10 nos seus níveis reais. T-QUAL-01 continua exigindo
   a jornada executada; a existência deste contrato ou de um seed não é PASS.

Não copiar números HOME-R1 como medições de UI-R1. As evidências anteriores podem
orientar o protocolo, mas precisam de nova execução e fonte/SHA explícitos.

## Dependências ainda abertas nesta preparação

UI-003 deve fechar chaves de grupo/filhos, novo alvo session, paginação e versões.
UI-004 deve fechar identidade/candidatos de conexão, formato de perfil legado e
intenção retomar/adicionar. Esses pontos definem quais construtores e stores a
fixture final deve usar. Não foi criado `fixtures.py` com um DTO antecipado nem
foram escritos testes que apenas repetiriam esse DTO. Nenhum cenário novo foi
promovido e nenhuma qualificação anterior foi descartada.

## Delta de coerência histórica para UI-020/029

A qualificação UI-005/PR00 foi preservada no commit `2cc70419`, incluindo
`pr00-fixture-qualification.json` e os hashes/medição antecedentes de54
statements/10.510 bytes. Esse commit recupera a fonte exata da amostra; ela não
é reatribuída às fontes posteriores.

Após revisão de UI-019, `fixtures.py::_read_facts` passou a gravar
`expected_revisions_json` da abertura/turns históricos com os mesmos
`ui-session-2`/`ui-binding-2` de suas colunas. O helper `copy_session` dos testes
também atualiza o session_id do scope copiado. São ajustes nos fatos sintéticos
próprios para inspeção exata; não criam admissão, lease, autoridade ou execução
nativa para a segunda sessão. Novos focais e hashes serão reportados como delta
separado; o antecedente PR00 permanece imutável.

Delta executado: `rtk proxy .venv\Scripts\python.exe -m pytest
tests/ui_simplification/test_fixtures.py
tests/ui_simplification/test_entry_relations.py
tests/ui_simplification/test_entry_layer_boundary.py -q -k
"not single_current_baseline_sample"`:20 PASS,1 deselected,53.70s
(tool `c68e33`, terminal0). Inclui os6 focais de fixture com assert novo do
scope de abertura,13 de relações e1 de fronteira de camadas. Nenhuma amostra
UI-005 foi repetida. SHA256 atual da fixture:
`7f8ca1874f7a87d7c70743c4404cc88bd3d212ea24ef5ab987ca075ae090bf20`;
teste de fixture:
`0aa009d225815330a32d2c7cd6314bea9b0469591491b951a331c7d1ad8dc0a3`;
helper/teste de relações:
`b3f4ced0c15ac5fc4060aa954713602fb889752eaa16f97861625f25bbb010fc`.
