# UI-005 — contrato de fixtures de PR-00

Estado: **preparação; implementação aguarda o fechamento de UI-003/UI-004**.
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
