# Matriz DX — SAFE-TRACE / AC01

Auditoria somente leitura dos 21 IDs originais. Nenhum teste/campanha foi executado, nenhum produto ou ledger foi editado. Recomendações abaixo não foram aplicadas.

As evidências selecionadas são PASS efetivamente presentes em XMLs retidos, ou relatórios de campanha identificados por hash. Cada teste em matrix.json inclui as assertions e/ou oráculos de exceção esperada atuais e suas linhas. Os PASS comprovam a campanha citada; esta leitura não requalifica automaticamente todos os bytes do pacote atual. Relatórios iniciais com falha continuam referenciados. Não somar campanhas sobrepostas como testes únicos.

Recomendação por requisito literal: contratos puros não herdam automaticamente a pendência produtiva de M1/M2. Mesmo os IDs recomendados VERIFIED abaixo não encerram AC01/full R3, cofre→cliente real ou M1/M2.

DX-T27, DX-T34 e DX-T39 permanecem NOT_RUN. O snapshot dos demais cenários DX pendentes, seus limites e relações temáticas está em pending-scenarios.json; nenhuma prova parcial da matriz encerra esses cenários automaticamente.

Dependência informada pelo root, não reavaliada nesta auditoria DX: no serviço atual, CLI/API/coordenador não expõem decisão explícita de força após timeout de drain exigida no plano, linha 325. Core.shutdown já possui escalada automática de contenção, que não substitui essa decisão. O caminho de parada controlada exige correção coordenada sem enfraquecer ownership/recuperação.

| ID | Ledger atual | Recomendação | Pendência do próprio ID |
|---|---|---|---|
| DX-01 | VERIFIED | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-02 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-03 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-04 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-05 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-06 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-07 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-08 | IMPLEMENTED | IMPLEMENTED | Qualificação real listada abaixo |
| DX-09 | IMPLEMENTED | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-10 | IMPLEMENTED | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-11 | IMPLEMENTED | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-12 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-13 | VERIFIED | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-14 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-15 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-16 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-17 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-18 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-19 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |
| DX-20 | IN_PROGRESS | IMPLEMENTED | Qualificação real listada abaixo |
| DX-21 | IN_PROGRESS | VERIFIED | Nenhuma lacuna literal demonstrada |

## DX-01

**Requisito literal** — plano fixo, linha 393.

**DX-01 — modelo declarativo próprio.** Criar um contrato puro para configurar clientes MCP externos, distinto de `HarnessHTTPTemplate` gerenciado. Campos: cliente/formato/versionamento, origem e endpoint aprovados, nome da entrada, mecanismo de referência de credencial e escopo de arquivo selecionado.

O Core pode abrigar esse contrato se ele for reutilizado por Server e Connector. A biblioteca não importa as aplicações, não lê credenciais, não faz HTTP, não modifica arquivos e não abre processos em importação. O host/CLI executa os efeitos autorizados.

Não aceitar uma chave `nxs_` fingindo ser `mcp-cap:`. Não relaxar `format_qualified` nem a proteção dos templates gerenciados. Não inferir que um cliente com suporte MCP tem adaptador de runtime correspondente.

**Implementação/reuso:** Contrato puro ParticipantClientConfig separado de HarnessHTTPTemplate, com cliente/build/formato/revisão, origem/endpoint, entrada, referência de ambiente e escopo. Exportação contém referências; contrato gerenciado mantém suas próprias guardas.

Fontes atuais:

- Core: `src/nexus_connector_core/participant_config.py:31` — `ParticipantClientConfig`.
- Core: `src/nexus_connector_core/participant_config.py:93` — `export_participant_config`.
- Core: `src/nexus_connector_core/config_document.py:63` — `plan_json_entry`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_participant_config.py:34` — `test_reference_only_round_trip_and_selected_entry_ownership`; 13 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-contract-core-installed.xml`.
- `tests/test_participant_config.py:140` — `test_participant_contract_cannot_substitute_for_managed_capability_or_qualification`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-contract-core-installed.xml`.
- `tests/test_participant_config.py:129` — `test_generic_export_is_manual_and_pi_has_no_invented_http_adapter`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-contract-core-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Requisito declarativo tem evidência correspondente. Campanhas cliente/cofre não são uma condição adicional deste contrato puro.

**Reconciliação de texto/status herdado:** O resultado histórico ainda diz participant init/launcher/recovery pendentes; esses produtos foram entregues em milestones posteriores. Os subscopes compartilhados de autenticação real não rebaixam o contrato puro.

## DX-02

**Requisito literal** — plano fixo, linha 399.

**DX-02 — matriz de formatos.** Na ampliação da frente DX, entregar dois formatos de clientes efetivamente testados, preferencialmente Claude Code e Codex, e exportação genérica para configuração manual. O primeiro marco pode usar um adaptador nativo já qualificado; não deve esperar esta ampliação para entregar daemon + preset + ciclo de trabalho pelo terminal. Verificar o formato nas versões usadas na campanha. A opção genérica não deve afirmar que instalou ou testou um cliente desconhecido. Pi segue sua integração suportada; não inventar MCP HTTP nativo para ele.

**Implementação/reuso:** Claude JSON, Codex TOML e exportação genérica manual implementados. Campanhas com binários reais leram configuração; outra campanha resolve referência sintética de ambiente e faz initialize autenticado, sem demonstrar a cadeia completa do launcher/cofre.

Fontes atuais:

- Core: `src/nexus_connector_core/participant_config.py:31` — `ParticipantClientConfig`.
- Core: `src/nexus_connector_core/participant_config.py:93` — `export_participant_config`.
- Nexus: `scripts/qualify_participant_formats.py:1`.
- Nexus: `plans/agent_ops/campaigns/participant-environment.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_participant_config.py:26` — `test_unobserved_build_is_explicitly_unknown_without_inventing_qualification`; 3 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-core-installed.xml`.
- `tests/test_participant_config.py:34` — `test_reference_only_round_trip_and_selected_entry_ownership`; 13 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-contract-core-installed.xml`.
- `tests/test_participant_config.py:129` — `test_generic_export_is_manual_and_pi_has_no_invented_http_adapter`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-contract-core-installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr04-participant-contract-client-formats.json`, `plans/agent_ops/evidence/pr04-participant-launch-native.json`, `plans/agent_ops/evidence/pr04-participant-guide/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Manter actual_client_credential_resolution NOT_RUN para cofre real -> CLI launch distribuído -> cliente real -> cooperação canônica; initialize com variável injetada manualmente não fecha a cadeia.
- Qualificar participação/cooperação dos dois clientes nas versões declaradas antes de fechar a frente M2; generic continua manual, sem promessa de cliente instalado.

**Recomendação:** IMPLEMENTED. Formatos e leitura por binários estão verificados; o aceite integral de clientes externos continua dependente da campanha declarada. Não é lacuna de implementação demonstrada.

**Reconciliação de texto/status herdado:** A prova antiga de parsing não deve apagar a prova posterior mais estreita de initialize; esta também não deve promover o subscope amplo de credenciais.

## DX-03

**Requisito literal** — plano fixo, linha 403.

**DX-03 — plan/apply.** Gerar diff redigido antes da alteração. Aplicar somente a entrada escolhida, preservando outros MCPs, preferências, comentários quando o formato permitir e configurações sem relação com Nexus. Não executar comandos recuperados do arquivo de configuração.

Registrar hash/revisão de entrada e exigir CAS na aplicação. Se o arquivo mudou desde a revisão, parar e refazer o plano. Usar gravação atômica, backup protegido e reversão somente das mudanças de propriedade desta operação. Uma segunda aplicação idêntica não cria duplicata.

O browser não deve fingir editar arquivos na máquina do usuário: gera orientações/configuração ou chama efeitos no host realmente autorizado. Alteração em cliente remoto é realizada no próprio host remoto. Caminho do Server não substitui caminho do cliente.

**Implementação/reuso:** Plans JSON/TOML com hash/CAS e ownership de entrada; persistência com lock, backup protegido, replace e observação de resultado incerto; compensação remove só entrada pertencente ao setup. Dashboard apenas gera orientação pública para executar no host escolhido.

Fontes atuais:

- Core: `src/nexus_connector_core/config_document.py:151` — `apply_json_plan`.
- Core: `src/nexus_connector_core/config_document.py:292` — `apply_toml_plan`.
- Core: `src/nexus_connector_core/config_persistence.py:170` — `_apply_plan_file`.
- Nexus: `src/okto_nexus/adapters/outbound/participant_files.py:1`.
- Nexus: `frontend/src/participantGuide.ts:40` — `buildParticipantGuide`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_config_persistence.py:41` — `test_create_and_update_preserve_source_backup_and_other_entries`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-core-installed.xml`.
- `tests/test_config_persistence.py:93` — `test_noncooperating_edit_during_apply_detected_before_replace`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-core-installed.xml`.
- `tests/test_config_persistence.py:17` — `test_host_protection_runs_before_sensitive_bytes_and_failure_preserves_source`; 8 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-core-installed.xml`.
- `tests/execution_r4/test_participant_removal.py:52` — `test_remove_only_owned_entry_preserves_other_values_and_server`; 13 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr04-participant-guide/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Plan/apply, CAS, preservação e compensação têm assertions e execução instalada; cliente efetivamente usar a credencial é DX-04/campanha separada.

**Reconciliação de texto/status herdado:** Marcações compartilhadas de cliente/MCP não representam escrita/configuração ainda não implementada. Limite documentado: writer não cooperante ainda pode correr na última janela compare/replace; não se promete transação global.

## DX-04

**Requisito literal** — plano fixo, linha 409.

**DX-04 — credenciais.** Importar a chave existente por prompt oculto, stdin ou referência de ambiente autorizada. Usar cofre do sistema quando disponível; fallback em arquivo restrito depende de consentimento explícito e política. Não criar chave permanente nova nem rotacionar a existente como efeito colateral de init.

Referência de ambiente no arquivo não basta: garantir e testar como o processo real do harness obtém o valor. Não dizer “pronto” se o launcher/GUI não herdar a variável. Não imprimir `export TOKEN=segredo`; explicar a instalação segura necessária. Exportações portáveis continuam sem chaves, grants ativos, caminhos e recibos de teste do host de origem.

Autenticação deve usar header Bearer. Selecionar a origem explicitamente, não seguir redirecionamento para enviar credencial a outro host. Respeitar a política de transporte atual do Server, alertar sobre plaintext e não afrouxá-la automaticamente. Corrigir o placeholder antigo do onboarding sem quebrar compatibilidade de clientes legados por mudança incidental.

**Implementação/reuso:** Importação protegida da chave existente; cofre escopado por perfil/setup; launcher fornece a referência só ao processo filho; Bearer para origem fixada sem redirects. Entrada pública do dashboard não inclui chave em comando/URL e não substitui entrega one-shot autorizada.

Fontes atuais:

- Nexus: `src/okto_nexus/adapters/inbound/cli/participant.py:1`.
- Nexus: `src/okto_nexus/adapters/outbound/participant_client.py:73` — `ParticipantVault`.
- Nexus: `src/okto_nexus/application/participant_launch.py:69` — `apply`.
- Nexus: `src/okto_nexus/adapters/outbound/participant_process.py:1`.
- Nexus: `frontend/src/participantGuide.ts:40` — `buildParticipantGuide`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_participant_init.py:228` — `test_cli_never_falls_back_to_echoing_key`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_init.py:279` — `test_actual_http_redirect_does_not_forward_bearer`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_launch.py:203` — `test_real_subprocess_receives_reference_without_parent_mutation`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_removal.py:310` — `test_windows_participant_vault_compensation_and_absent_replay`; 6 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed-final.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr04-participant-launch-native.json`, `plans/agent_ops/evidence/pr04-participant-guide/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Linha 411 exige testar como o processo real do harness obtém o valor: ainda falta juntar cofre do SO real, launcher distribuído e cliente real na mesma campanha.
- GUI/TUI herança/reload e cooperação canônica de cliente real não foram qualificados; resultados atuais devem continuar UNKNOWN quando não observados.

**Recomendação:** IMPLEMENTED. Há provas separadas de vault Windows, processo filho e initialize real com env sintético; não existe a prova composta exigida. Sem novo defeito concreto de produto demonstrado.

**Reconciliação de texto/status herdado:** actual_client_credential_resolution VERIFIED em alguns IDs é o subscope estreito de variável sintética/initialize; participant_os_vault_client_end_to_end continua NOT_RUN. Não tratá-los como equivalentes.

## DX-05

**Requisito literal** — plano fixo, linha 438.

**DX-05 — init.** Preservar o caminho explícito/compatível de participante, compartilhando a implementação de setup com connect. Escolher Server, identidade e workspace; validar identidade; produzir/revisar configuração; aplicar com consentimento; orientar restart/reconnect do cliente quando necessário; validar o nível realmente alcançado. Uma identidade ausente exige criação explícita pelo operador usando os serviços existentes. O `init` de agente não se autoeleva a operador.

Persistir `setup_run_id` e progresso não secreto suficiente para retomar a mesma configuração. A preparação não autoriza tarefas nem inicia o modelo. Se a identidade já tiver runtime, acrescentar um cliente participante não deve desligar o runtime globalmente ou substituir bindings existentes. Informar que o endereço é a identidade, não o cliente: acrescentar um canal não garante que ele será o consumidor de cada mensagem. Preservar a seleção e a reserva exclusiva da entrega lógica já existentes; não fan-out para todos os meios da mesma identidade. Uma identidade separada só é criada quando o operador explicitamente deseja outro agente, não como solução automática para ambiguidade de transporte.

**Implementação/reuso:** init participant e connect participant usam TerminalParticipant; selecionam identidade/workspace existentes por Bearer, revisam contexto e arquivo, aplicam por aprovação exata e mantêm checkpoints. Ausência/autoridade incompatível recusa, sem criação implícita ou elevação.

Fontes atuais:

- Nexus: `src/okto_nexus/adapters/inbound/cli/participant.py:1`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/connect.py:120` — `run_connect`.
- Nexus: `src/okto_nexus/application/terminal_participant.py:68` — `review`.
- Nexus: `src/okto_nexus/application/terminal_participant.py:92` — `apply`.
- Nexus: `src/okto_nexus/application/participant_setup.py:12` — `participant_context`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_participant_init.py:207` — `test_init_and_connect_participant_share_review_and_cli_checkpoints`; 8 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_init.py:106` — `test_participant_context_uses_bearer_identity_without_self_elevation`; 5 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_init.py:76` — `test_review_apply_reconnect_preserves_runtime_and_other_configuration`; 12 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Qualificação de participante real com reload, credencial obtida no contexto efetivo e cooperação; a implementação já informa configuração aplicada separadamente de cliente/MCP/trabalho comprovados.

**Recomendação:** IMPLEMENTED. O caminho de produto está implementado e seus contratos locais instalados passaram; manter aceite integral de participante pendente, sem inventar lacuna de API.

**Reconciliação de texto/status herdado:** Resultado antigo que diz init/launcher ausentes foi superado; a pendência atual é qualificação da cadeia real.

## DX-06

**Requisito literal** — plano fixo, linha 442.

**DX-06 — sem transação distribuída fictícia.** Identidade no Server, cofre local e arquivos do cliente não participam da mesma transação. Registrar etapas e compensações explícitas. Não chamar o setup inteiro de atômico. Preservar o Finish transacional que já existe para a parte gerenciada. Falha local não autoriza apagar uma identidade preexistente no Server.

**Implementação/reuso:** Estados review/credential_pending/credential_stored/file_pending/done gravam intenção antes de cada efeito; retomada observa efeito incerto. Remoção tem file_pending/vault_pending e aposenta perfil antes de compensar. Finish gerenciado mantém transação canônica no Server.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_participant.py:92` — `apply`.
- Nexus: `src/okto_nexus/application/participant_removal.py:1`.
- Nexus: `src/okto_nexus/application/connection_setup.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_participant_init.py:146` — `test_lost_checkpoint_resumes_same_intent_by_observing_effect`; 7 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_init.py:171` — `test_vault_failure_leaves_file_and_server_intact_and_retains_intent`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_removal.py:86` — `test_lost_removal_checkpoint_recovers_without_restoring_or_rewriting`; 6 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_terminal_identity.py:173` — `test_late_finish_failure_rolls_back_identity_key_and_every_setup_object`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. O requisito é a separação das etapas e recuperação/compensação, diretamente exercitadas. Não exige uma transação distribuída nem uma campanha produtiva para validá-las.

**Reconciliação de texto/status herdado:** Pendências compartilhadas de cliente/cofre fim a fim não são falta de checkpoints ou compensação.

## DX-07

**Requisito literal** — plano fixo, linha 446.

**DX-07 — doctor estruturado.** Retornar checagens independentes com `PASS`, `FAIL`, `UNKNOWN` ou `NOT_APPLICABLE`, motivo e próxima ação:

| Nível | O que demonstra | O que não demonstra |
|---|---|---|
| Serviço local | Instância, supervisor, versão e prontidão quando verificáveis | Harness autenticado ou tarefa executada |
| Endereço acessível | Reachability e versão anunciada | Autenticação ou capacidade de executar |
| Identidade autenticada | Credencial válida para o agente correto | Permissão para qualquer ação |
| Configuração do cliente | Entrada válida e referência de segredo resolvível no contexto testado | Cliente já recarregou o arquivo |
| MCP negociado | Transporte inicializado e superfície compatível | Modelo chamou as ferramentas |
| Participação comprovada | Agente abriu sua sessão/trocou a mensagem de teste | Handoff concluído |
| Handoff de teste comprovado | Claim e resultado canônicos correlacionados | Qualificação de todos os cenários de runtime |

Doctor padrão não inicia o daemon, não instala serviço, não inicia inferência, não envia trabalho, não abre processo de harness, não executa probes sem consentimento e não modifica configuração. Checks ativos ficam explícitos e explicam efeito/custo. Distinguir resultado desconhecido de falha comprovada.

**Implementação/reuso:** ProjectDiagnostics/ParticipantDiagnostics mantêm checagens independentes; modos ativos explícitos e default passivo. Adaptador comum v1 controla status/código/reason/next_action, preservando legado e separando metadata de prova.

Fontes atuais:

- Nexus: `src/okto_nexus/application/project_diagnostics.py:114` — `inspect_project`.
- Nexus: `src/okto_nexus/application/participant_diagnostics.py:52` — `inspect_participant`.
- Nexus: `src/okto_nexus/domain/diagnostic_report.py:1`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/doctor.py:1`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/participant_doctor.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_participant_doctor.py:35` — `test_passive_doctor_preserves_files_without_vault_http_process_or_recovery`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_participant_doctor.py:116` — `test_actual_tcp_mcp_is_not_agent_participation_or_model_work`; 11 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-removal-installed.xml`.
- `tests/execution_r4/test_project_diagnostics.py:29` — `test_ready_connection_does_not_prove_provider_login_participation_or_work`; 8 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-project-doctor-installed.xml`.
- `tests/test_diagnostic_report_contract.py:28` — `test_common_artifact_digest_and_emitted_vocabulary`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr10-correlation/installed/diagnostics/installed.xml`.
- `tests/test_doctor_diagnostic_format.py:29` — `test_managed_legacy_shape_and_exit_are_unchanged`; 11 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr10-correlation/installed/diagnostics/installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr10-correlation/diagnostics/shared-contract-comparison.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. As checagens provam apenas o nível observado e mantêm UNKNOWN para o resto. Falta de campanha produtiva é resultado honesto do diagnóstico, não ausência deste requisito.

**Reconciliação de texto/status herdado:** participant_client_validation/participant_mcp_and_cooperation_checks IMPLEMENTED têm provas posteriores instaladas; consolidar nomes sem promover participação real.

## DX-08

**Requisito literal** — plano fixo, linha 460.

**DX-08 — smoke de cooperação.** Oferecer teste opcional com correlação própria. Validar primeiro uma troca dirigida e depois um handoff explicitamente consentido. O resultado válido é a cadeia canônica observada, não a presença de uma string na resposta do modelo. Não mudar o teste gerenciado `NEXUS_CONNECTION_OK` para prometer o que ele não prova.

**Implementação/reuso:** TerminalCooperation exige consentimento separado para troca dirigida e handoff, persiste IDs antes de enviar, observa reply/claim/resultado canônicos e preserva incerteza. Doctor lê histórico sem qualificá-lo como fato atual.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_cooperation.py:153` — `review_exchange`.
- Nexus: `src/okto_nexus/application/terminal_cooperation.py:297` — `review_handoff`.
- Nexus: `src/okto_nexus/application/terminal_cooperation.py:320` — `_handoff_evidence`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/cooperation.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_cooperation_cli.py:123` — `test_separate_consents_canonical_reply_after_other_session_ack_and_claim_result`; 29 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-cooperation-facade-cli-installed.xml`.
- `tests/execution_r4/test_cooperation_cli.py:184` — `test_text_or_unrelated_reply_cannot_qualify_exchange`; 4 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr04-cooperation-facade-cli-installed.xml`.
- `tests/test_terminal_cooperation.py:228` — `test_exchange_consent_never_authorizes_handoff`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-cooperation-facade-cli-installed.xml`.
- `tests/test_terminal_cooperation.py:376` — `test_completion_requires_exact_scope_peer_claim_and_result`; 3 oráculos (assert/raises); 9 caso(s) PASS em `plans/agent_ops/evidence/pr04-cooperation-facade-cli-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Executar cooperação com os clientes externos qualificados e operadores/autorização apropriados; testes atuais usam peers/atores sintéticos, não demonstram comportamento de um modelo real.

**Recomendação:** IMPLEMENTED. Mecanismo e prova canônica estão exercitados; o smoke real de cooperação M2 continua NOT_RUN. Nenhuma nova falha concreta do mecanismo encontrada.

**Reconciliação de texto/status herdado:** Não confundir NEXUS_CONNECTION_OK gerenciado ou texto gerado com a cadeia de cooperação nova.

## DX-09

**Requisito literal** — plano fixo, linha 478.

**DX-09 — cliente fino, não orquestrador.** Implementar fachada reutilizável por CLI e scripts. Comunicação direta com o Server via transportes existentes; pode usar MCP HTTP como cliente, nunca como proxy. Escolher uma superfície canônica por operação e documentá-la. Não escrever diretamente nas tabelas a partir da CLI remota nem duplicar regras de domínio.

A identidade vem da autenticação; `--to` escolhe destinatário, nunca ator. Campos de sessão/contexto devem preservar proveniência e afinidade existentes. Não abrir uma sessão nova por comando se isso mudar involuntariamente a conversa. Perfis/sessões explícitos devem expor o ciclo de vida; um processo observador não mantém falsamente vivo um agente que não está participando.

Não adivinhar intenção por LLM: `message send` é conversa/informação; `handoff create` é trabalho. Não converter estratégia de roteamento em broadcast para obter execução automática. Handoffs dirigidos, broadcast e claim MCP continuam usando os comportamentos existentes.

**Implementação/reuso:** CLI coordination/work delega a fachadas de aplicação e clientes HTTP/MCP; ator vem da credencial, destino não substitui principal; sessão/contexto aprovados ficam vinculados ao request. A CLI remota não grava domínio SQLite nem implementa servidor/proxy MCP.

Fontes atuais:

- Nexus: `src/okto_nexus/adapters/inbound/cli/coordination.py:1`.
- Nexus: `src/okto_nexus/application/terminal_coordination.py:177` — `submit`.
- Nexus: `src/okto_nexus/adapters/outbound/participant_coordination_mcp.py:1`.
- Nexus: `src/okto_nexus/application/terminal_work.py:78` — `submit`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_coordination_cli.py:101` — `test_commands_resume_latest_and_explicit_new_request_preserve_private_content`; 17 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:265` — `test_explicit_session_context_survives_resume_without_storing_its_secret`; 5 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:477` — `test_handoff_visibility_is_preserved_by_canonical_creation`; 3 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:490` — `test_workspace_visibility_is_rejected_before_any_server_effect`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Cliente fino e fronteiras de ator/escopo possuem prova instalada correspondente. Campanha combinada nativa/externa é aceite M1/M2 separado, não uma segunda implementação da fachada.

**Reconciliação de texto/status herdado:** Renovação remota e rotação já entregues; qualificações produtivas permanecem abertas nos IDs de ciclo, sem reapresentá-las como fachada faltante.

## DX-10

**Requisito literal** — plano fixo, linha 486.

**DX-10 — verificar e complementar deduplicação.** Mapear o caminho real de criação de mensagens/handoffs. Reutilizar mecanismo existente apenas se sua chave, escopo e transação forem compatíveis com uma requisição de coordenação. Caso contrário, adicionar `client_request_id` opcional às entradas apropriadas e um recibo canônico mínimo.

Chave lógica: instalação + ator autenticado + workspace + operação + `client_request_id`. Hash semântico exclui segredos, mas inclui alvo, conteúdo e contexto relevantes. Mesmo ID/hash retorna a decisão/objeto existente; mesmo ID com conteúdo diferente conflita. Retentativa continua sujeita à autenticação e visibilidade atuais.

O recibo deve ser confirmado na **mesma transação** da mensagem/handoff, inbox/outbox, evento e contabilização aplicáveis. Não implementar “criar por HTTP e gravar recibo depois”, nem um lock em memória que desaparece no restart.

A decisão `pending_approval` também é deduplicada: não criar segunda aprovação. A execução posterior usa o caminho existente, preservando a identidade da requisição e autoridade original. Campos internos de bypass de aprovação nunca se tornam parâmetros da CLI/API.

Retenção de recibos deve ser explícita, limitada e compatível com a retenção dos recursos. Dentro da janela garantida, um recurso removido não pode ser recriado pela repetição: responder com referência/tombstone apropriada. Fora da janela, o cliente recusa replay automático e exige revisão; não alegar idempotência infinita ou exactly-once de efeitos externos.

A CLI grava o ID antes de transmitir. Resposta perdida é tratada por consulta do mesmo ID. Não gerar novo ID automaticamente em timeout. Em Server antigo sem esse contrato, diagnosticar a limitação e não oferecer replay seguro fictício.

**Implementação/reuso:** CoordinationRequestKey/hash semântico e recibo na UoW de criação; chave inclui instalação/ator/workspace/operação/request. CLI salva ID/hash antes da transmissão e só reinspeciona a mesma identidade dentro da janela. Pending approval/tombstone e autenticação corrente preservados.

Fontes atuais:

- Nexus: `src/okto_nexus/domain/coordination_requests.py:39` — `CoordinationRequestKey`.
- Nexus: `src/okto_nexus/application/coordination_requests.py:30` — `CoordinationCreation`.
- Nexus: `src/okto_nexus/adapters/outbound/sqlite/coordination_requests.py:34` — `SqliteCoordinationRequestRepo`.
- Nexus: `src/okto_nexus/application/terminal_coordination.py:177` — `submit`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_coordination_creation.py:62` — `test_same_request_concurrent_retry_recovers_one_canonical_object`; 10 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-creation-release-installed.xml`.
- `tests/test_coordination_creation.py:129` — `test_commit_cuts_leave_no_partial_creation`; 5 oráculos (assert/raises); 6 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-creation-installed.xml`.
- `tests/test_coordination_requests.py:408` — `test_semantic_hash_preserves_content_target_and_context`; 5 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-receipts-installed.xml`.
- `tests/test_coordination_requests.py:248` — `test_message_pruning_preserves_tombstone_and_refuses_replacement`; 5 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-receipts-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:169` — `test_real_process_death_after_commit_recovers_through_installed_entrypoint`; 12 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.
- `tests/test_terminal_coordination.py:333` — `test_not_found_after_original_local_or_server_deadline_refuses_replay`; 4 oráculos (assert/raises); 4 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-behavior-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Dedupe transacional/retentativa limitada não depende de inferência para ser verificado. Não promove exactly-once de efeitos externos nem campanha produtiva.

**Reconciliação de texto/status herdado:** Subscopes herdados de M1 e renovação não indicam deduplicação ainda ausente; nova prova remota complementa autoridade corrente.

## DX-11

**Requisito literal** — plano fixo, linha 500.

**DX-11 — espera correlacionada.** `handoff wait` observa o handoff identificado, seu resultado e verificação quando exigida. Para operação nativa, quando exposta, observar `operation_id` exato. Mensagem entregue/lida não é execução concluída; um futuro `message --wait` deve exigir condição explícita, como entrega, leitura ou resposta correlacionada.

Timeout encerra a espera, não cancela o trabalho. Ctrl+C encerra o observador; cancelamento exige comando explícito. Resposta do cliente deve incluir IDs recuperáveis e estado atual. Estado incerto é distinto de falha e de sucesso.

Evitar corrida entre snapshot e assinatura: usar cursor e releitura canônica, cobrindo conclusão antes de a espera iniciar. Não depender apenas de um evento futuro. Respeitar long-poll/capacidades da versão instalada e o orçamento de conexões. Nunca manter transação SQLite aberta durante uma espera de rede.

Saída JSON deve ser estável. Códigos de saída precisam distinguir comando válido, erro de uso, recusa, timeout de observação e resultado incerto sem conflitar silenciosamente com convenções existentes. Documentar a matriz exata após revisar o parser atual.

**Implementação/reuso:** Wait usa ID exato, cursor antes do snapshot e releitura canônica; acompanha verificação/resultado sem inferir conclusão de delivery/idle. Timeout/interrupt encerram observador, com IDs e estado incerto recuperáveis; saída/exitcodes documentados/testados.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_coordination.py:241` — `_wait_handoff`.
- Nexus: `src/okto_nexus/application/terminal_coordination.py:271` — `wait_request`.
- Nexus: `src/okto_nexus/application/terminal_work.py:233` — `observe`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/coordination.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_terminal_coordination.py:378` — `test_wait_captures_cursor_before_snapshot_and_detects_existing_completion`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-behavior-installed.xml`.
- `tests/test_terminal_coordination.py:403` — `test_wait_timeout_keeps_nonterminal_work_and_never_cancels_or_creates`; 4 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-behavior-installed.xml`.
- `tests/test_terminal_coordination.py:534` — `test_delivery_read_and_native_idle_events_never_complete_handoff_wait`; 5 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-behavior-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:423` — `test_wait_interrupt_or_unknown_read_does_not_cancel_or_resubmit`; 5 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.
- `tests/execution_r4/test_coordination_cli.py:509` — `test_usage_errors_have_exit_two_and_no_server_effect`; 4 oráculos (assert/raises); 7 caso(s) PASS em `plans/agent_ops/evidence/pr05-coordination-cli-release-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Contrato de observação e saídas tem testes correspondentes sem exigir um provider real para produzir estados canônicos sintéticos.

**Reconciliação de texto/status herdado:** Campanha M1/M2 combinada continua aberta; não confundi-la com implementação ou teste do observador.

## DX-12

**Requisito literal** — plano fixo, linha 510.

**DX-12 — UI orientada à intenção.** Evoluir a introdução atual em coerência com connect: projeto/harness e o mesmo preset; “usar meu cliente existente” continua disponível. O dashboard consome o mesmo setup, identidade, configuração e estados, sem obrigar a troca do terminal para o navegador em qualquer etapa do uso padrão. Abrir o painel posteriormente não inicia outro onboarding nem cria outro agente. Mostrar capacidades/resultados comprovados, não um único selo verde que mistura todos os níveis. Manter configurações avançadas acessíveis e opcionais.

**Implementação/reuso:** Introdução lê o preset canônico; identidade existente evita novo intro; personalização usa objetos atuais. Caminho cliente existente usa guia público com origem real e comandos existentes, sem executar efeito remoto ou emitir prontidão fictícia.

Fontes atuais:

- Nexus: `frontend/src/components/onboarding/OnboardingModal.tsx:12` — `OnboardingModal`.
- Nexus: `frontend/src/components/ParticipantGuide.tsx:7` — `ParticipantGuide`.
- Nexus: `frontend/src/participantGuide.ts:40` — `buildParticipantGuide`.
- Nexus: `src/okto_nexus/application/project_preset.py:54` — `read_project_preset`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_project_dashboard.py:18` — `test_project_recommendation_is_the_terminal_contract_and_applies_nothing`; 7 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-project-dashboard-installed.xml`.
- `tests/execution_r4/test_project_dashboard.py:43` — `test_dashboard_personalization_and_terminal_reopen_preserve_identity_history_and_grants`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-project-dashboard-installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr03-project-dashboard-browser.json`, `plans/agent_ops/evidence/pr04-participant-guide/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Browser real contra pacote instalado verificou a UI e preservação de identidade/configuração; isso não promove uso efetivo de cliente/provedor.

**Reconciliação de texto/status herdado:** Placeholder e snippets com segredo/origem inadequada foram substituídos no milestone do guia. DX-12 ainda IN_PROGRESS sem subscope aberto é status global candidato a reconciliação.

## DX-13

**Requisito literal** — plano fixo, linha 512.

**DX-13 — caminho gerenciado.** Reutilizar Connections e seu Finish. Não ressuscitar `automatic_reply` como opção independente; o código atual normaliza esse campo. Não aplicar política runtime=false ao agente inteiro somente porque ele recebeu outro participante externo.

**Implementação/reuso:** Connections/Finish existentes continuam kernel gerenciado; configuração é normalizada pelo contrato comum. Participante adiciona entrada/credencial local sem desabilitar runtime de toda identidade.

Fontes atuais:

- Nexus: `src/okto_nexus/application/connection_setup.py:1`.
- Nexus: `src/okto_nexus/application/terminal_connection.py:198` — `apply`.
- Nexus: `src/okto_nexus/application/participant_setup.py:12` — `participant_context`.
- Core: `src/nexus_connector_core/connection_configuration.py:37` — `parse_connection_configuration`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_participant_init.py:76` — `test_review_apply_reconnect_preserves_runtime_and_other_configuration`; 12 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-nexus-installed.xml`.
- `tests/execution_r4/test_terminal_connect.py:62` — `test_review_requires_exact_consent_then_finish_and_reconnect_preserve_configuration`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr04-participant-init-nexus-installed.xml`.
- `tests/execution_r4/test_project_preset_update.py:106` — `test_disabled_runtime_stays_disabled_without_test_or_grant`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-preset-evolution-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Manter VERIFIED: os invariantes específicos têm execução instalada e não exigem nova rota gerenciada.

**Reconciliação de texto/status herdado:** Nenhuma pendência concreta neste ID; limites de ciclo real pertencem a DX-20/M1.

## DX-14

**Requisito literal** — plano fixo, linha 514.

**DX-14 — Connector.** Preservar `connect/configure/status/doctor`, aprovação assíncrona e vault existentes, integrando-os a SVC-11 e DX-15…21. Melhorar mensagens e referência aos mesmos códigos de diagnóstico. Somente compartilhar contrato declarativo onde há benefício real; não copiar uma nova implementação de credenciais/conexão para cada aplicação. Alterações no Core exigem pins/locks e testes coordenados, não mudança de NXL sem necessidade.

**Implementação/reuso:** Connector conserva connect/configure/status/doctor, cofre e aprovação assíncrona; reuse verifica identidade/epoch/binding atuais. Diagnóstico v1 comum opt-in preserva legado/exitcodes e evita tradução cega de warn. Remote bootstrap/renewal integram controles existentes.

Fontes atuais:

- Connector: `src/okto_nexus_connector/cli/commands/connect.py:57` — `run_connect`.
- Connector: `src/okto_nexus_connector/cli/commands/connect_reuse.py:171` — `completed_remote_reuse`.
- Connector: `src/okto_nexus_connector/cli/commands/configure_local.py:72` — `configure_local`.
- Connector: `src/okto_nexus_connector/cli/commands/doctor.py:1`.
- Connector: `src/okto_nexus_connector/cli/diagnostic_report.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/unit/test_connect_reuse.py:69` — `test_bare_connect_reuses_project_and_current_authority_without_rewrite`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-connector-reconnect-connector-installed.xml`.
- `tests/unit/test_diagnostic_report_contract.py:94` — `test_default_legacy_shape_and_call_graph_are_preserved`; 13 oráculos (assert/raises); 1 caso(s) PASS em `../okto-nexus-connector/docs/evidence/diagnostics-v1/installed.xml`.
- `tests/unit/test_diagnostic_report_contract.py:174` — `test_no_probe_does_not_resolve_credentials_or_contact_server`; 3 oráculos (assert/raises); 1 caso(s) PASS em `../okto-nexus-connector/docs/evidence/diagnostics-v1/installed.xml`.
- `tests/unit/test_diagnostic_report_contract.py:275` — `test_shared_artifacts_match_the_installed_contract_pin`; 4 oráculos (assert/raises); 1 caso(s) PASS em `../okto-nexus-connector/docs/evidence/diagnostics-v1/installed.xml`.
- `tests/execution_r4/test_remote_renewal.py:33` — `test_remote_renewal_lost_issue_recovers_one_grant_without_migrating_session`; 20 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-renewal/candidate-v2/nexus/installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr10-correlation/diagnostics/shared-contract-comparison.json`, `plans/agent_ops/evidence/pr03-remote-renewal/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Integrações de produto/contrato preservadas e qualificadas em pacotes. Campanha nativa SVC/M1 remota permanece separada e não é promovida.

**Reconciliação de texto/status herdado:** Todos os subscopes próprios listados já VERIFIED; descrições antigas de diagnóstico não alinhado e renovação remota ausente foram superadas.

## DX-15

**Requisito literal** — plano fixo, linha 430.

**DX-15 — connect como entrada principal.** Implementar a fachada que resolve perfil/topologia, chama SVC para iniciar/reutilizar o serviço local apropriado e conduz o setup pelo terminal. Usar os serviços e autorizações atuais; não duplicar o Finish gerenciado. Aplicar o preset de DX-18/19 e encaminhar diretamente ao percurso de trabalho de DX-20. O dashboard é uma opção durante todo o uso padrão; seus links não substituem controles de terminal necessários a decisões rotineiras. Instalações já configuradas reutilizam o vínculo e não repetem o wizard. Política organizacional preexistente que imponha outro canal permanece válida e é diagnosticada separadamente.

**Implementação/reuso:** connect resolve perfil/projeto/topologia, inicia/reutiliza o dono apropriado e delega revisão/Finish; existente reusa binding sem wizard. Rotas locais, operador remoto e Connector compartilham preset e encaminham à CLI work.

Fontes atuais:

- Nexus: `src/okto_nexus/adapters/inbound/cli/connect.py:120` — `run_connect`.
- Nexus: `src/okto_nexus/application/terminal_connection.py:45` — `review`.
- Nexus: `src/okto_nexus/application/remote_terminal_setup.py:19` — `RemoteProjectSetup`.
- Connector: `src/okto_nexus_connector/cli/commands/connect.py:57` — `run_connect`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/test_terminal_connect_process.py:12` — `test_connect_starts_reuses_and_leaves_service_owned_until_explicit_stop`; 16 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_terminal_connect.py:197` — `test_interactive_connect_enters_work_only_after_configuration`; 9 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/unit/test_connect_reuse.py:69` — `test_bare_connect_reuses_project_and_current_authority_without_rewrite`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-renewal/candidate-v1/connector/installed.xml`.
- `tests/execution_r4/test_remote_setup_integration.py:51` — `test_operator_and_connector_cli_complete_same_root_once`; 53 oráculos (assert/raises); 6 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/nexus/installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- M1 real instalado, local e via Connector: serviço persistente + preset + trabalho/decisão/resultado/reabertura, sem dashboard e sem configuração manual; não executado.
- Campanhas nativas de início no login/SVC permanecem separadas; seleção/recusa da opção já tem prova de contrato.

**Recomendação:** IMPLEMENTED. Fachada está entregue; falta qualificar o percurso padrão real ao qual este ID encaminha. Sem nova lacuna concreta de implementação encontrada.

**Reconciliação de texto/status herdado:** Bootstrap de identidade remota, revisão única, retomada, renovação e rotação já entregues; não os listar como produto ausente.

## DX-16

**Requisito literal** — plano fixo, linha 432.

**DX-16 — descoberta e revisão mínima.** Detectar pasta atual e executáveis suportados no host correto; a existência no PATH é descoberta, não qualificação nem login confirmado. Reutilizar a escolha anterior ou pré-selecionar uma recomendação válida; havendo ambiguidade material, pedir somente a escolha necessária. Mostrar projeto/workspace, harness, identidade sugerida ou reutilizada, efeito de execução e mudanças de configuração em um resumo revisável. Permitir escolher início no login nessa mesma revisão, sem tornar instalação de serviço um pré-requisito. A autorização já válida é reutilizada; criação de agente, ampliação de escopo e autorização de execução são ações explícitas nos serviços existentes, reunidas na mesma revisão quando o operador possui autoridade.

**Implementação/reuso:** Resolução de projeto/candidato no host correto, recomendação única quando não ambígua e escolha pontual quando necessária. Revisão inclui identidade/workspace, configuração/efeitos, grants e início no login; PATH permanece somente descoberta.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_connection.py:45` — `review`.
- Connector: `src/okto_nexus_connector/cli/commands/connect.py:225` — `_choose_harness`.
- Connector: `src/okto_nexus_connector/cli/commands/configure_local.py:72` — `configure_local`.
- Nexus: `src/okto_nexus/application/remote_terminal_setup.py:39` — `review`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/unit/test_connect_project_review.py:34` — `test_one_detected_installation_is_recommended_without_executing_or_prompting`; 3 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/connector/installed.xml`.
- `tests/unit/test_connect_project_review.py:49` — `test_material_ambiguity_asks_once_and_preserves_exact_candidate`; 2 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/connector/installed.xml`.
- `tests/unit/test_connect_project_review.py:145` — `test_one_project_review_submits_existing_canonical_defaults`; 12 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/connector/installed.xml`.
- `tests/execution_r4/test_terminal_identity.py:219` — `test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-policy-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Campanha de instalação nova com harness/provedor realmente prontos e configuração efetiva no host local/remoto; os testes de recomendação atuais usam inventário/candidatos sintéticos e não confirmam login.

**Recomendação:** IMPLEMENTED. Contrato de descoberta/revisão está verificado; qualificação do caminho padrão com instalação real continua pendente no escopo R3.

**Reconciliação de texto/status herdado:** Não confundir escolha/revisão de início no login entregue com campanha real de login não executada.

## DX-17

**Requisito literal** — plano fixo, linha 434.

**DX-17 — progresso, retomada e primeira sessão.** Preservar `setup_run_id`, revisões e recibos do fluxo atual. Mostrar etapas verificáveis: serviço pronto → identidade/vínculo autorizado → configuração aplicada → harness/sessão pronta → interação disponível no terminal. Se ocorrer perda de resposta, consultar o mesmo setup antes de repetir. Distinguir “serviço disponível”, “cliente precisa recarregar”, “aguardando aprovação” e “sessão pronta”; nenhum deles equivale a tarefa concluída. Login de provedor ausente exige instrução concreta no contexto do usuário, sem tentar autenticar uma pessoa dentro do daemon. Depois da conexão, permitir a primeira solicitação real e seu acompanhamento conforme DX-20; o smoke continua opcional e consentido. Não enviar trabalho automaticamente.

O fluxo padrão do terminal é: executar `connect` na pasta → confirmar o resumo necessário → trabalhar com o agente e acompanhar o resultado. Não há um passo “abra o dashboard para terminar de configurar”. Uma política ou falha real pode exigir intervenção adicional, mas não acrescentar perguntas apenas para reproduzir conceitos internos. No host do Connector, integrar seu CLI existente ao percurso, apontando para o Server remoto configurado; decisões de operador podem ocorrer em outro terminal autenticado, sem transportar sua credencial para esse host.

**Implementação/reuso:** Setup/profile persiste IDs/revisões/recibos, observa resposta perdida, distingue estados e não reenvia teste incerto. Work guarda request/operation exatos; diagnóstico não confunde serviço, sessão e tarefa. Reconnect e renovação consultam autoridade atual.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_connection.py:160` — `observe`.
- Nexus: `src/okto_nexus/application/remote_terminal_setup.py:97` — `recover_review`.
- Nexus: `src/okto_nexus/application/terminal_work.py:186` — `resume`.
- Nexus: `src/okto_nexus/application/project_diagnostics.py:114` — `inspect_project`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_terminal_connect.py:87` — `test_response_loss_resumes_without_repeating_native_effects`; 5 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_terminal_connect.py:102` — `test_submitted_test_with_lost_cache_is_not_replayed`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_project_diagnostics.py:96` — `test_ready_session_open_is_not_a_productive_result`; 6 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-project-doctor-installed.xml`.
- `tests/execution_r4/test_terminal_work.py:82` — `test_lost_submission_response_recovers_same_work_without_duplicate_dispatch`; 5 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Primeira solicitação real, progresso/decisão/resultado e reencontro após restart com provider efetivo no serviço local e no Connector; sessões/peers sintéticos não são M1.

**Recomendação:** IMPLEMENTED. Retomada/proveniência foram exercitadas; a primeira sessão produtiva real obrigatória não foi qualificada.

**Reconciliação de texto/status herdado:** terminal_grant_renewal e remote_terminal_grant_renewal genéricos ainda aparecem IN_PROGRESS apesar dos subscopes específicos VERIFIED. Consolidar sem fechar M1.

## DX-18

**Requisito literal** — plano fixo, linha 524.

**DX-18 — preset generalista de projeto.** Definir um preset pequeno e versionado, resolvido para a configuração comum do produto antes da aplicação. Não introduzir um “modo simples” com armazenamento, autoridade ou executor próprios. O preset deve ser útil sem especialização posterior; nome, papel, ferramentas adicionais e políticas mais sofisticadas ficam disponíveis como ajustes opcionais.

| Aspecto | Padrão proposto | Regra de aplicação |
|---|---|---|
| Identidade | Nome legível sugerido a partir de harness/projeto, com `agent_id` persistente. | Reutilizar vínculo canônico já configurado. Criar identidade nova somente como ação explícita do operador no resumo inicial; não associar só por nome ou pasta. |
| Projeto e workspace | Pasta atual e workspace canonicamente associado, quando houver. | Se faltar workspace, incluir sua criação autorizada ou seleção necessária na mesma revisão; nunca presumir que igualdade de caminhos comprova acesso. |
| Papel | Assistente generalista capaz de realizar o trabalho solicitado no projeto. | Não exigir persona ou especialidade. O perfil não é um agente global compartilhado entre usuários ou projetos. |
| Harness | Modelo, instruções do projeto, ferramentas e políticas já configurados e suportados na rota escolhida. | Validar a configuração efetiva no processo real; diferenças de launcher/serviço devem ser explicadas antes do uso. Não remover sandbox nem desabilitar decisões nativas. |
| Trabalho no projeto | Ler, editar e executar ferramentas conforme as permissões efetivas do harness e a autorização do usuário. | O preset não vira um assistente apenas de leitura, mas também não amplia automaticamente acesso a outros projetos, shell, rede ou credenciais. |
| Coordenação Nexus | Descoberta dos colaboradores visíveis, própria inbox, contexto autorizado, mensagens e participação em handoffs no workspace aprovado. | Mapear cada ação ao catálogo e aos contratos atuais; claim, resultados, destinatários e admissão continuam sujeitos às políticas canônicas. |
| Execução gerenciada | Permitir sessões para trabalho autorizado nesse projeto, incluindo solicitações elegíveis de colaboradores autorizados quando esse for o perfil aprovado. | Explicar esse efeito no resumo, usar grants/admissão atuais e respeitar revogação. Estar online não autoriza executar qualquer mensagem recebida. |
| Operação | Serviço sob demanda, controles pelo terminal e opção explícita de início no login. | O serviço continua independente do painel. Diagnóstico não inicia trabalho e o setup não dispara um turno produtivo. |

O agente deve receber identificação e instruções mínimas para usar a coordenação disponível, pelos mecanismos de configuração/contexto já suportados. Não reescrever a personalidade do harness nem sobrescrever instruções do projeto para impor uma persona Nexus. Instruções e descrições de ferramentas orientam comportamento; a autoridade é verificada pelos serviços, nunca pelo prompt.

**Implementação/reuso:** Preset project-generalist revision 1 resolve identidade/permissões/configuração para contratos comuns; defaults preservam modelo/instruções existentes, decisões nativas e limites de autorização. Novo agente/workspace só na revisão/Finish autorizados, sem associação por nome/pasta.

Fontes atuais:

- Nexus: `src/okto_nexus/application/project_preset.py:24` — `identity_defaults`.
- Nexus: `src/okto_nexus/application/project_preset.py:36` — `configuration`.
- Nexus: `src/okto_nexus/application/project_preset.py:44` — `effects`.
- Nexus: `src/okto_nexus/application/remote_setup.py:149` — `bootstrap`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_terminal_identity.py:35` — `test_finish_creates_one_reviewed_identity_and_recovery_never_rotates_its_key`; 26 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-policy-installed.xml`.
- `tests/execution_r4/test_terminal_identity.py:114` — `test_colliding_identity_is_never_adopted_or_modified`; 5 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-policy-installed.xml`.
- `tests/execution_r4/test_terminal_identity.py:173` — `test_late_finish_failure_rolls_back_identity_key_and_every_setup_object`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-policy-installed.xml`.
- `tests/execution_r4/test_remote_setup_integration.py:51` — `test_operator_and_connector_cli_complete_same_root_once`; 53 oráculos (assert/raises); 6 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/nexus/installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- Validar configuração efetiva no processo real lançado pelo serviço e demonstrar utilidade do preset com trabalho completo local/remoto, sem ampliar permissões ou substituir instruções; aceitação M1 ainda NOT_RUN.

**Recomendação:** IMPLEMENTED. Preset/autoridade estão implementados; a cláusula de configuração efetiva e utilidade real não é provada por serialização/configuração sintética.

**Reconciliação de texto/status herdado:** remote_terminal_grant_renewal NOT_RUN é obsoleto para o contrato de renovação: os subscopes remote_grant_renewal_http_ipc_wss e rotation_completed_reuse já passaram. Não altera a pendência produtiva.

## DX-19

**Requisito literal** — plano fixo, linha 539.

**DX-19 — uma revisão significativa para aplicar o preset.** Resolver os defaults e mostrar um resumo legível de identidade, projeto/workspace, harness e o que o Nexus poderá iniciar ou encaminhar ali. Reunir criação autorizada de agente/workspace, participação e configuração de execução quando necessárias; o usuário não percorre formulários administrativos separados para cada objeto. Oferecer expansão dos detalhes e edição opcional, sem transformar todos os campos internos em perguntas.

Usar o mesmo `setup_run_id`, revisão, autorização e Finish existente. Uma confirmação de produto cobre efeitos concretos previamente mostrados; não transforma as etapas de Server/cofre/host em transação distribuída. Se a autorização ou a configuração mudar antes do commit, refazer a parte afetada da revisão. Operador sem autoridade recebe a pendência real; participante não pode criar agentes ou conceder grants para eliminar a pendência. O preset não concede administração global, mudança de políticas ou aprovação dos próprios pedidos ao agente. Reabrir o setup após resposta perdida recupera o mesmo resultado, sem novos agentes ou permissões.

**Implementação/reuso:** Revisão local/remota reúne identidade/workspace, configuração e autorização; usa IDs/revisões canônicos e Finish. Bootstrap remoto operador-only entrega chave one-shot separada do JSON/checkpoint; perda retorna material indisponível, nunca rotação/recriação implícita.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_connection.py:45` — `review`.
- Nexus: `src/okto_nexus/application/remote_terminal_setup.py:39` — `review`.
- Nexus: `src/okto_nexus/application/remote_terminal_setup.py:258` — `apply`.
- Nexus: `src/okto_nexus/application/remote_setup.py:149` — `bootstrap`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/remote_setup_io.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_terminal_identity.py:219` — `test_default_cli_review_is_stable_and_reconnect_preserves_identity_customizations`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-policy-installed.xml`.
- `tests/test_remote_setup_server.py:121` — `test_participant_and_revoked_principal_cannot_read_or_bootstrap`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v3/nexus/installed.xml`.
- `tests/test_remote_setup_server.py:236` — `test_failure_rolls_back_agent_workspace_epoch_and_checkpoint`; 3 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v3/nexus/installed.xml`.
- `tests/test_remote_setup_server.py:109` — `test_lost_response_recovers_same_references_never_key_or_rotation`; 4 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v3/nexus/installed.xml`.
- `tests/execution_r4/test_remote_setup_integration.py:51` — `test_operator_and_connector_cli_complete_same_root_once`; 53 oráculos (assert/raises); 6 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-bootstrap/candidate-v1/nexus/installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. A revisão única e suas fronteiras de consentimento/autoridade/recovery têm evidência integrada correspondente. Trabalho efetivo após ela pertence ao aceite DX-18/20/M1.

**Reconciliação de texto/status herdado:** A antiga limitação 'remote identity/workspace bootstrap missing' foi resolvida no milestone e607d012/7091ef2 e complementada pela renovação.

## DX-20

**Requisito literal** — plano fixo, linha 543.

**DX-20 — ciclo cotidiano completo no terminal.** Disponibilizar, no caminho padrão qualificado, solicitar trabalho e continuar a conversa, acompanhar o estado, responder a perguntas, aprovar ou recusar pedidos autorizados, obter resultado e reencontrar trabalho/sessão ao voltar. Preferir a interação nativa já suportada pelo harness; quando a rota gerenciada não a expuser, implementar a menor fachada CLI necessária sobre as operações, perguntas, decisões e consultas canônicas existentes. Não criar um histórico de conversa paralelo nem interpretar logs/prompts como comandos de controle.

Cada decisão deve preservar principal autorizado, ID do pedido, revisão, validade, escopo, correlação e opções canônicas. Resposta livre enviada ao modelo não substitui endpoint de aprovação. Uma pergunta ao agente continua destinada ao agente; um terminal participante não toma decisões de operador. O operador pode usar outro CLI autenticado, sem distribuir suas credenciais ao Connector ou ao harness. Perguntas/permissões rotineiras do padrão precisam de uma apresentação no terminal; um link obrigatório para o painel não satisfaz esse requisito.

Submissão e acompanhamento mantêm a identidade da requisição e da operação ou handoff. Antecipar da DX-09…11 somente a fachada, deduplicação, correlação e espera usadas por M1, reutilizando os recibos nativos comprovados quando suficientes. Não oferecer uma nova submissão com retry inseguro para depois corrigir na PR-05. Persistir a referência antes de transmitir quando o contrato permitir; uma resposta perdida leva a inspeção/recuperação do mesmo pedido. Se a versão não permitir recuperar o resultado com segurança, expor incerteza e não repetir produtivamente.

Fechar o CLI encerra a observação, não cancela a execução pertencente ao serviço. Ao voltar, reencontrar perfil, `agent_id`, workspace e referências canônicas de conversa/trabalho; retomar a sessão quando isso for suportado. Se a sessão não puder ser retomada, apresentar o resultado/estado recuperado e a opção explícita de nova sessão com o contexto autorizado disponível, sem fingir continuidade nem repetir a tarefa anterior. Não prometer attach à TUI original, adoção de processo externo ou sobrevivência a reboot sem qualificação específica.

Um adaptador que apenas inicia o processo, mas obriga o usuário a abrir o dashboard para trabalhar ou decidir pedidos normais, não qualifica a rota padrão de M1. Completar a fachada mínima ou escolher outra rota já suportada que cumpra o ciclo, mantendo os contratos de execução. O objetivo não exige desenvolver um multiplexer PTY. Colaboração usa os caminhos canônicos disponíveis no preset; expansão para outros clientes e comandos genéricos permanece em M2.

**Implementação/reuso:** Fachada work usa operações/sessões/perguntas/decisões canônicas, preserva ator/revisão/escopo e resposta perdida. Sair interrompe só observação; reopen recupera IDs/resultados, sem attach/continuidade inventada ou envio automático.

Fontes atuais:

- Nexus: `src/okto_nexus/application/terminal_work.py:78` — `submit`.
- Nexus: `src/okto_nexus/application/terminal_work.py:233` — `observe`.
- Nexus: `src/okto_nexus/application/terminal_work.py:292` — `decide`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/work.py:1`.
- Nexus: `src/okto_nexus/adapters/inbound/cli/native_input.py:1`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_terminal_work.py:320` — `test_interactive_cli_request_question_answer_result_and_return`; 11 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_terminal_work.py:116` — `test_native_decision_response_loss_recovers_canonical_result_and_keeps_answers_out_of_profile`; 18 oráculos (assert/raises); 3 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_terminal_work.py:248` — `test_leaving_interactive_cli_does_not_interrupt_or_close_service_owned_work`; 4 oráculos (assert/raises); 2 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.
- `tests/execution_r4/test_terminal_work.py:58` — `test_send_result_reopen_continue_and_close_share_canonical_session`; 11 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-terminal-work-installed.xml`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

- DX-T39/T40/T43/T45/T46/T47/T50 no percurso padrão real instalado local e via Connector, com serviço persistente, provider autorizado, pergunta/permissão representativa, resultado e reabertura; campanha M1 não executada.

**Recomendação:** IMPLEMENTED. Produto/fachada e isolamento são exercitados com peer sintético; isso não substitui o caminho padrão qualificado explicitamente exigido pelo ID.

**Reconciliação de texto/status herdado:** CLI de trabalho/decisões e renovação já existem. A pendência atual é campanha real, não construir outro histórico/orquestrador.

## DX-21

**Requisito literal** — plano fixo, linha 553.

**DX-21 — preservar configuração e permitir evolução opcional.** Guardar a origem/revisão do preset nos mecanismos de configuração existentes, quando necessário para explicar sua aplicação. Reconectar não reaplica defaults, troca modelo, reseta nome/papel/permissões ou cria outra identidade. Atualização futura de preset não amplia acesso automaticamente: apresentar diff dos efeitos e reaproveitar o fluxo autorizado. Evitar uma nova infraestrutura genérica de templates para suportar esse único preset.

O dashboard e o CLI leem os mesmos objetos. Alterar especialização, nome ou opções na interface mantém identidade, histórico e vínculos, sujeito às revisões e autorizações canônicas. O usuário que nunca personaliza continua podendo executar o ciclo padrão indefinidamente, enquanto suas credenciais e políticas permanecerem válidas. Documentação de início rápido deve terminar em trabalho útil e explicar apenas os controles necessários; administração avançada é opcional.

# 9. Frente ATN — central de atenção

**Implementação/reuso:** Origem/revisão/defaults do preset ficam no setup existente; merge de três vias só propõe defaults não customizados, revisão lista efeitos/autoridades e Finish usa CAS. Reconnect lê configurações atuais; dashboard personaliza mesmos objetos. Renovação preserva escopo/revogação e não reaplica preset.

Fontes atuais:

- Nexus: `src/okto_nexus/application/project_preset_update.py:19` — `merge_defaults`.
- Nexus: `src/okto_nexus/application/project_preset_update.py:79` — `review_in_uow`.
- Nexus: `src/okto_nexus/application/terminal_preset.py:71` — `apply`.
- Nexus: `src/okto_nexus/application/terminal_connection.py:38` — `current`.
- Connector: `src/okto_nexus_connector/cli/commands/connect_reuse.py:171` — `completed_remote_reuse`.

Testes/assertions e PASS retidos (expressões exatas em matrix.json):

- `tests/execution_r4/test_project_preset_update.py:48` — `test_review_advances_only_unchanged_defaults_and_finish_recovers_once`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-preset-evolution-reconnect-installed.xml`.
- `tests/execution_r4/test_project_preset_update.py:82` — `test_concurrent_change_refuses_finish_without_repair_or_authority`; 4 oráculos (assert/raises); 4 caso(s) PASS em `plans/agent_ops/evidence/pr03-preset-evolution-installed.xml`.
- `tests/execution_r4/test_project_preset_update.py:106` — `test_disabled_runtime_stays_disabled_without_test_or_grant`; 7 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-preset-evolution-installed.xml`.
- `tests/execution_r4/test_project_dashboard.py:43` — `test_dashboard_personalization_and_terminal_reopen_preserve_identity_history_and_grants`; 14 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-project-dashboard-installed.xml`.
- `tests/execution_r4/test_remote_renewal.py:153` — `test_remote_revocation_keeps_recovered_receipt_historical_and_participant_cannot_renew`; 9 oráculos (assert/raises); 1 caso(s) PASS em `plans/agent_ops/evidence/pr03-remote-renewal/candidate-v2/nexus/installed.xml`.

Relatórios complementares: `plans/agent_ops/evidence/pr03-project-dashboard-browser.json`, `plans/agent_ops/evidence/pr03-remote-renewal/reports.json`.

**Lacuna de produto:** Nenhuma lacuna concreta adicional demonstrada pela revisão deste requisito; distinguir as qualificações listadas de produto ausente.

**Qualificação pendente:**

Nenhuma campanha adicional necessária para o requisito literal indicado; os aceites gerais permanecem separados.

**Recomendação:** VERIFIED. Preservação/evolução opcional têm provas de contrato, UI instalada e recovery. Não significa promessa de execução infinita, reboot ou aceite produtivo M1.

**Reconciliação de texto/status herdado:** Renovação remota/rotação e atualização de preset não são mais lacunas de produto; consolidar os rótulos genéricos antigos, mantendo as campanhas reais em seus IDs.
