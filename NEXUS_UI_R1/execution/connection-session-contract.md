# UI-004 — Contrato de escolha de conexão e sessão

Contrato de PR-00 para R09, R10, R11, R12 e R17. A leitura integral do [plano UI-R1](../PLANO_CODEX_NEXUS_UI_SIMPLIFICADA_HOME_ONBOARDING_R1.md), especialmente §§8–10, e da tarefa UI-004 do [ledger](../NEXUS_UI_EXECUTION_LEDGER_R1.json) precedeu este documento. O aceite desta tarefa é documental: rastrear a tabela de decisão aos handlers reais e definir o delta. Não certifica a implementação nem executa T-CLI-01/05/11 ou T-CONN-01.

## Corte e instruções

Inspeção estática em 2026-11-16:

| Repositório | Branch / HEAD inspecionado | Relação com o plano |
|---|---|---|
| Nexus | `feature/v0.3.5`, `9de55d950739ed5d7348e946506e4c05464ccb13` | Posterior ao snapshot `3d95aad8`; baseline/bump coordenados em PR-00. |
| Connector | `feature/v0.0.13`, `414e3e7c126941603678c7ac51a06c3e0f13b616` | Posterior ao snapshot `a8bd48bd`; preserva o fluxo remoto existente. |
| Core | Pin `0.0.14`, sem mudança proposta aqui | Nenhuma lacuna de protocolo demonstrada nesta inspeção. |

Nexus tinha `.gitattributes` modificado e `NEXUS_UI_R1/` não rastreado; Connector estava limpo. Esses estados pertencem à execução coordenada e não foram restaurados. Foram lidos RTK, CONTRIBUTING e CI de ambos, inclusive a política de origem de PR do Connector. Nenhum `AGENTS.md` adicional foi encontrado nos diretórios ancestrais acessíveis ou nas árvores dos dois repositórios, excluindo ambientes/dependências. Todos os shells usaram RTK.

A CI Nexus valida frontend e artefatos instalados em Windows/Linux, Python 3.11–3.13, quatro shards. A CI Connector valida limites sem MCP, suites Windows/Linux e lifecycle macOS, seguida de build. Sua contribuição prevê PR em `develop` e promoção própria a `main`; este contrato não altera governança. A documentação antiga que descreve o CLI Nexus como stdio e o resumo gerado do Connector que diz “JSON optional” não prevalecem sobre os handlers atuais: os wizards Connector rejeitam JSON/noninteractive. Não foram executadas suites, serviços, credenciais, inferência ou comandos de instalação nesta tarefa.

## Vocabulário e chave de seleção

| Entidade | Identidade / significado | Não substituir por |
|---|---|---|
| Destino | Origem normalizada, `server_id` confirmado; contexto local de instância/home ou `operator_profile` remoto selecionado | Mesmo hostname, porta presumida, pasta ou nome amigável. |
| Operador | Identidade humana autenticada no destino e seu contexto de credencial | Nome do profile local; autoridade da chave de agente. |
| Projeto | Pasta absoluta local do atalho e `workspace_id` canônico, quando conhecido | Nome da pasta como autorização sobre workspace. |
| Conexão | `server_id`, `agent_id`, `executor_id`, `binding_id`, `workspace_id`, `workspace_binding_id`; no remoto também associação/realização confirmadas | Só agent ID, alias, harness, PID ou hostname. |
| Profile / alias | Atalho/checkpoint local recuperável, com rótulo humano separado | Nova identidade canônica ou armazenamento de histórico/chave. |
| Sessão | Escopo da conexão mais `session_id`; conferir executor e workspace no retorno | Primeira sessão, mais recente, sessão de outro binding. |
| Pedido | `client_intent_id`, hash, resolução e `operation_id` associados | Novo ID de tentativa para esconder resposta perdida. |

O catálogo proposto seleciona candidatos por **destino + instância confirmada + contexto humano + projeto** antes de comparar harness. Metadado local incompleto é candidato não confirmado, nunca prova de posse/permissão. No destino local, a instância do service manager não se confunde com `server_id`; mudança de PID/geração também não cria outra conexão. A confirmação canônica deve recusar Server diferente ou escopo alterado. Não abrir vaults de outros usuários nem enumerar identidades alheias para preencher o catálogo.

## Intenções independentes

| Intenção | Seleção e leitura prévia | Efeito autorizado | Recuperação / vedação | Handler real a reutilizar |
|---|---|---|---|---|
| Retomar conexão | Atalho explícito ou escolha humana da conexão; revalidar Server, binding e configuração atual | Reusar contexto e lifecycle permitido por `connect`; oferecer trabalho depois | Não reaplicar preset, criar identidade, refazer teste nem renovar grant. Pendente retoma sua etapa original. | Nexus `saved_selection`, `TerminalConnection.observe`, `RemoteTerminalConnection`; Connector `saved_request`, `verify_binding`, `completed_remote_reuse`. |
| Adicionar conexão | Intenção nova explícita, harness/host/projeto; reservar atalho e ID uma vez | Revisar setup; teste somente consentido; Finish canônico cria o que a revisão contém | Conexão anterior intacta. Nunca converter em Replace, renovar a anterior ou adotar agente por nome. | Nexus `TerminalConnection.review/apply`, `connection_setup`; Connector `configure_local`, `connect_setup` e onboarding existente. O picker/reserva são novos. |
| Continuar sessão | Escolha exata dentre sessões autorizadas da conexão; revalidar `control_available` e escopo | Enviar texto pelo intent canônico dessa sessão, após pedido explícito | Observação não envia; sessão fechada/incompatível retorna histórico/recusa, sem troca de contexto. | `TerminalWork.sessions/session/submit`; `runtimeApi`/composer; Connector `RuntimeAdmission.execute` com `turn.submit`. |
| Nova sessão | Escolha explícita sem `session_id`; respeitar binding, política e grant atuais | `runtime.start` / abertura canônica, com texto somente se fornecido | Não é adicionar conexão; não cria grant. Sem pedido/ação explícita, conexão sem sessão continua sem sessão. | `work send --new-session`; API resolve/submit; Connector `runtime start --new-session`. |
| Recuperar envio incerto | Ler checkpoint e mesmo `client_intent_id` antes de oferecer outra tarefa | Consultar receipt; admitir somente a resolução original ainda não admitida conforme contrato | Não gerar ID/texto/session alternativos. Se resolução não existe, reapresentar exatamente o pedido original; nunca replay automático do teste. | `TerminalWork.resume`, `submit` pendente; Connector `RuntimeAdmission.inspect/execute`; setup recover separado. |

Seleção de conexão precede seleção de sessão. `work resume` recupera envio, não escolhe outra sessão nem “continua a última”. O `TerminalWork` atual pode usar o `session_id` lembrado no checkpoint: isso é referência durável específica, não ordenação por data; o novo picker deve mostrá-la e obter a escolha Continuar/Nova antes de um pedido de contexto ambíguo. O Server ainda valida políticas canônicas de reuso; a apresentação não promete abrir contexto novo quando houve reuso nem restauração nativa não suportada.

## Decisão obrigatória de connect (§8) e delta rastreado

| Entrada / estado | Resultado contratado | Atual / mudança necessária |
|---|---|---|
| Zero conexões compatíveis | Seleção curta de harness e revisão; perfil técnico gerado sem pergunta | `project_profile` usa `project-` + SHA256(path)[:24]; adicionar catálogo/reserva sem renomear o legado. |
| Uma conexão, sem seletor | Retomar / Adicionar outra / Cancelar | Nexus atualmente adota o profile derivado; Connector `saved_request` retorna candidato único automaticamente. Inserir escolha anterior ao setup. |
| Várias conexões | Lista com harness, agente, host e estado; escolha exata | Connector já pergunta entre requests retidos; acrescentar opção Adicionar. Nexus ainda não possui catálogo multiconexão por projeto. |
| `--profile` existente e compatível | Seleção explícita, manter scripts e recuperação | Reusar `saved_selection`; bypass do picker de conexão, sem bypass de revisão ou escolha de sessão necessária. |
| `--profile` existente, `--client` incompatível | `PROFILE_CONFLICT` e orientação para Adicionar | Manter recusa; não reinterpretar profile explícito como novo. |
| `--client claude`, só Codex implícito | Oferecer Adicionar Claude sem pedir nome técnico | Resolver antes do profile implícito; hoje conflito cai em `saved_selection`. |
| Um ou vários candidatos do mesmo harness | Retomar um identificado ou adicionar outra instância | Filtrar candidatos não seleciona o primeiro nem torna todos equivalentes. |
| `--new-connection` explícito | Preparar atalho próprio, sugerir colaborador novo por padrão; sessão só depois de pedido | Flag proposta, **ausente no parser atual**. Em script exigir `--profile` explícito estável. |
| Profile de adição já reservado | Recuperar mesmo setup se origem/versionamento/conteúdo correspondem | Novo metadado local de origem; profile legado ou de outra intenção conflita, sem overwrite. Não acrescentar request-ID obrigatório ao connect Nexus. |
| Checkpoint pendente/incerto | Recuperar original antes de novo envio/setup | Reusar estados/receipts existentes; uma adição independente exige intenção explícita e preserva o pendente. Não oferecer novo como correção da falha. |
| Escritor ativo | `PROFILE_BUSY` / observação permitida por contrato | `ExclusiveFileLock` por profile existe; não apagar `.guard`, clonar ou desligar outra sessão para escapar. |
| Revogado, expirado, indisponível ou drift | Motivo e recuperação explícitos | Reusar validações atuais. Configurar/autorizar novamente é revisão separada; indisponibilidade não significa zero candidatos. |
| JSON/noninteractive sem escolha suficiente | Envelope redigido `selection_required`, sem prompt nem criação de agente/binding/grant/trabalho | Novo resultado de CLI, preservar códigos atuais; não inventar código no enum fechado de domínio. Destino/profile/client isoladamente podem ainda ser insuficientes. |
| Cancelar antes do teste/Finish | Sem novo agente/binding/grant/tarefa | Explicar efeitos locais já realizados: serviço iniciado por connect ou identidade importada explicitamente no Connector podem permanecer. |

Alias interativo novo deve ser único, persistido uma vez antes de efeitos, com rótulo legível e nome técnico exibido depois para scripts. Reservar sob lock/CAS curto do catálogo; depois lock existente por profile. Não manter lock global durante interação/rede. Revalidar catálogo e revisão após interação. Checkpoints legados `project-<hash>` permanecem legíveis, sem renomear agent/binding/intent/receipt, nem criar novo histórico paralelo. O índice, se necessário, é reconstruível e não autoridade.

## IDs, revisões e checkpoints preservados

| Caminho real | Conteúdo / gate atual | Regra para o novo seletor |
|---|---|---|
| Nexus `terminal/profiles/PROFILE.json`, gravação `atomic_json`, lock `PROFILE.guard` | Seleção, `server_id`, request `client_intent_id`, `review_revision`, `review_request`, estados `review/approved/check_submitted/test_submitted/finish/done`, receipt | Reservar atalho antes dos efeitos; mesmo ID e corpo após crash. `--approve` deve coincidir com SHA256 da revisão exata; conteúdo/revisão alterados exigem revisão. |
| Setup local canônico | `baseline`: `execution_revision`, `runtime_revision`, `defaults_revision`, `binding_revision`, `endpoint_revision`; instalação `candidate_ref/inventory_revision`; política nativa `expected_revision` | Preservar CAS, testes e Finish/recover. Nova identidade é criada apenas no Finish transacional; defaults e permissões aparecem na revisão. |
| Nexus `terminal/work/PROFILE.json` | `scope`, `session_id`; slots work/control com request hash/context sem texto, resolução (`client_intent_id`, `operation_id`, `resolution_revision`, `intent_hash`); decisão/autorização separadas | Não persistir prompts/respostas/output. Ler incerteza antes de abrir vault/cliente; novo picker não descarta slots. Repetição com corpo/seleção diferentes conflita. |
| Setup remoto Nexus + Connector | `setup_run_id`, `draft_revision`, handoff, child request map, baseline/proofs, bootstrap/Finish e entrega única de material | Preservar root; `--review-current` revisa os efeitos alterados no mesmo root, sem regenerar child IDs por conta própria. Handoff público não é credencial. |
| Connector `StateStore` | Identidades/Server/executor/realization/binding/runtime intents e `preferences['configure.SERVER.AGENT.REQUEST']`, `remote-setup.ROOT`; lock e snapshot atômico | Usar `update` sob lock para mutação concorrente, revalidar snapshot depois da autenticação. Não usar full `save` de snapshot antigo para sobrescrever outros writers. |
| Binding remoto atual | Server/executor/agent/endpoint/workspace/workspace binding/adapter/candidate/inventory/realization/binding revision; authorization/configuration revisions atuais separadas | `verify_binding` compara mapa aprovado; receipt histórico não reautoriza grant revogado. `/me` confirma Server/agente/credential epoch. |
| Runtime/decisão | Intent resolve→admission; approval ID, approval key, recipient, expiry, CAS/review e native decision receipt | Revalidar no submit. Texto ao modelo não aprova permissão; operador não personifica agente. Registrada não significa aplicada nativamente. |
| Login/startup | Checkpoint próprio, revisão do usuário/host/task e resultado independente do setup | Retomar sem reinstalar/habilitar silenciosamente. Setup configurado pode coexistir com `login_start_pending`. |

`--plan` pode persistir revisão não secreta quando o Server já é consultável, mas não inicia serviço, probe ou modelo. Ausente, retorna limite `service_not_ready`, sem criar substituto. Normal `connect` pode iniciar/reusar serviço antes da revisão; eventual `effects_started=false` futuro só é válido se nenhum efeito ocorreu. `work` inspeciona, não inicia serviço. Exit 0 não prova trabalho concluído: no Nexus pode significar plano, configuração, admissão ou cancelamento normal; 2 é gramática, 3 recusa/incompleto e 130 Ctrl+C. JSON conserva stdout estruturado e mensagens humanas no canal adequado.

## Scripts explícitos

Exemplos de contrato, **não executados nesta tarefa**. Maiúsculas são valores obtidos do ambiente/leituras autorizadas, não defaults inventados. Em script, o chamador seleciona deliberadamente o profile/alias estável; a experiência interativa não pede ao usuário que o invente. Acrescentar `--home NEXUS_HOME` ou `--state-dir CONNECTOR_STATE` explícitos em instalações isoladas conforme cada parser.

### Nexus: comandos já existentes

```sh
# Retomar o atalho escolhido, sem prompt de trabalho.
okto-nexus connect --profile PROFILE --project PROJECT --no-chat --json
# Inspecionar as sessões da conexão, depois escolher SESSION_ID explicitamente.
okto-nexus work sessions --profile PROFILE --json
okto-nexus work send --profile PROFILE --session-id SESSION_ID --request-id INTENT_ID --message "Continuar este contexto" --json
# Contexto novo é outra intenção, sem SESSION_ID.
okto-nexus work send --profile PROFILE --new-session --request-id NEW_INTENT_ID --message "Começar outro contexto" --json
# Recuperar original sem reenviar outro texto/ID.
okto-nexus work resume --profile PROFILE --json
okto-nexus work status --profile PROFILE --session-id SESSION_ID --json
# Revisar uma configuração explicitamente selecionada; não inicia Server.
okto-nexus connect --profile PROFILE --client codex --project PROJECT --plan --json
okto-nexus connect --profile PROFILE --approve REVIEW_REVISION --no-chat --json
```

Não usar os dois últimos comandos para substituir um profile incompatível. No fluxo atual, um profile novo pode propor criação de identidade; `--agent AGENT_ID --binding-id BINDING_ID` seleciona reuso autorizado. Um atalho para binding remoto já aprovado usa `--operator-profile OP --agent AGENT_ID --binding-id BINDING_ID`; sua pasta local identifica o atalho, não o launch path remoto.

### Nexus: sintaxe nova a implementar, não disponível no corte

```sh
# Interativo: alias gerado, revisão humana e nenhuma abertura de sessão implícita.
okto-nexus connect --new-connection --client claude --project PROJECT
# Script: PROFILE é escolhido pelo chamador uma vez e retido nas repetições.
okto-nexus connect --new-connection --profile PROFILE --client claude --project PROJECT --plan --json
okto-nexus connect --new-connection --profile PROFILE --approve REVIEW_REVISION --no-chat --json
```

`--provider-home HOST_LOGIN_DIRECTORY`, quando exigido, refere-se ao host de execução e não autentica automaticamente o provedor. Se faltar escolha/instalação, recusar/solicitar seleção; não inventar um caminho ou habilitar teste. Repetir `--new-connection --profile PROFILE` recupera apenas a intenção de adição correspondente, não transforma profile legado em origem nova.

### Connector: sintaxes reais, sem paridade artificial de flags

```sh
# Wizard interativo e recuperação da mesma configuração remota.
okto-nexus-connector connect --identity IDENTITY_ALIAS --project HOST_PROJECT --request-id REQUEST_ID
okto-nexus-connector configure --identity IDENTITY_ALIAS --request-id REQUEST_ID
# Runtime R4: alias é o binding escolhido, não profile Nexus nem identity alias.
okto-nexus-connector runtime status --alias BINDING_ALIAS --json
okto-nexus-connector runtime inspect SESSION_ID --alias BINDING_ALIAS --json
okto-nexus-connector runtime submit SESSION_ID "Continuar este contexto" --alias BINDING_ALIAS --client-intent-id INTENT_ID --json
okto-nexus-connector runtime start BINDING_ALIAS --new-session --client-intent-id NEW_INTENT_ID --text "Começar outro contexto" --json
okto-nexus-connector runtime operation --alias BINDING_ALIAS --client-intent-id INTENT_ID --json
```

`runtime operation` inspeciona a intenção existente; a retomada de admissão usa o mesmo comando/corpo/ID conforme `RuntimeAdmission`, não um inexistente `work resume` no Connector. Os exemplos R4 usam alias explícito: ramos legados sem associação R4 podem acionar IPC/lifecycle e não são o contrato de leitura proposto para seleção. `reconnect` do Connector reinicia graciosamente o daemon de todas as conexões configuradas; não é sinônimo do botão Retomar uma conexão.

`connect` e `configure` rejeitam `--json` e `--non-interactive` antes de acessar credenciais. O seletor novo preserva essa recusa. Para automação de configuração **no host Server**, o comando atual é:

```sh
okto-nexus-connector --non-interactive connection-config apply --file connection.json --identity OPERATOR_ALIAS --agent AGENT_ID --request-id REQUEST_ID --executor-id EXECUTOR_ID --candidate-ref CANDIDATE_REF --inventory-revision INVENTORY_REVISION --project SERVER_PROJECT --workspace-id WORKSPACE_ID --json
```

Essa identidade é operador importado nesse cliente, não a chave de agente do host remoto. O comando não é apresentado como automação equivalente de bootstrap de host Connector. Para este, os caminhos atuais de wizard/host draft permanecem interativos; não inventar `--profile` ou novo `--json` no Connector.

### Bootstrap remoto existente: autoridades em terminais distintos

```sh
# Host Connector, sem chave de operador; preparação passiva e revisão local.
okto-nexus-connector connect --server SERVER_URL --setup-draft host-draft.json --request-id ROOT_ID --project HOST_PROJECT
# Cliente do operador: planejar, aprovar revisão exata, exportar handoff público.
okto-nexus connect --operator-profile OP --remote-draft host-draft.json --profile PROFILE --plan --json
okto-nexus connect --profile PROFILE --approve REVIEW_REVISION --setup-receipt-output handoff.json --no-chat --json
# Host: handoff autenticado e chave canônica por entrada protegida, se necessária.
okto-nexus-connector connect --setup-receipt handoff.json
# Cliente do operador: acompanhar o MESMO root/profile até o Finish do host.
okto-nexus connect --profile PROFILE --no-chat --json
```

O bootstrap não entrega chave de operador ao host. O material canônico de agente é de entrega única: perda não autoriza emissão/rotação implícita. Para proposta remota de binding já existente, o operador pode obter `okto-nexus operator approval APPROVAL_ID --profile OP --json` e decidir com `--decision approve --confirm REVIEW_REVISION --json`; o Connector mantém sua credencial de participante. Aprovação pendente não é Ready. Fechar terminal não cancela root/daemon/execução.

## Máquina, superfície e autoridade

| Superfície | Host e autoridade | Reuso real | Delta obrigatório |
|---|---|---|---|
| Nexus CLI local | Embedded executor no host Server; operador local autorizado | `resolve_terminal_target`, service manager, `TerminalConnection`, `TerminalWork`, autorização e checkpoints existentes | Catálogo/retomar-adicionar antes de `project_profile`; reserva durável; flag explícita; picker de sessão separado de recovery. Nenhum dashboard necessário. |
| Nexus CLI operador remoto | Cliente humano remoto; Server selecionado por `operator_profile` | `RemoteTarget.inspect/ensure_running` só verifica remoto; `RemoteTerminalConnection`, `RemoteProjectSetup` | Isolar catálogo por destino/humano; nenhuma opção local de serviço no remoto; binding aprovado só cria atalho local. Offline nunca vira Server local substituto. |
| UI no browser | Browser pode estar em computador diferente; operador autenticado no Server | `AgentConnectionsPanel`, `connectionConfiguration`, `runtimeApi` setup/test/Finish; `connectionSessions`, `SessionClosures`, composer e controles atuais | Fluxo curto Home Retomar/Adicionar; “Neste servidor” é host Server, “Em outra máquina” encaminha Connector. Nova identidade/revisão devem usar contratos existentes; não simular criação trocando somente rótulos do formulário por agente. Preservar intenção em resposta perdida e refresh. |
| Connector host | Executor remoto e chave canônica do agente, `credential_epoch`; registro/máquina sujeitos à política Server | `connect_reuse`, `configure_local`, `StateStore`, `connect_setup`, `BindingOnboarding`, daemon/lifecycle | Retomar/Adicionar antes de `binding_conflicts.resolve_conflict` (Replace/Abort); alias próprio reservado sem nome técnico obrigatório; escolher/bootstrap autorizado de colaborador novo. Não revogar vínculo/máquina anterior implicitamente. |
| UI/terminal de decisão | Operador próprio no Server ou cliente remoto autorizado | Approval review/revision/CAS e mesmo binding apply/Finish | Aprovação alcançável no básico/terminal; não introduzir operador secreto no Connector nem decisão local automática. |

“Cliente que já uso” é modo participante, não nova runtime gerenciada. Pasta de projeto, provider home e descoberta pertencem ao host executor; JSON portátil v2 exclui identidade/segredos/máquina/instalação/workspace/pastas. Importar preferências não concede grant nem copia path remoto. Configuração pronta, daemon ativo, sessão aberta, capacidade, turno executando e resultado concluído são estados separados. Login permanece ação explícita e limitada às plataformas qualificadas; adicionar não cria daemon por profile, não reinstala tarefa e não renova orçamento.

## Fontes rastreadas e aceite de PR-00

Fontes Nexus no HEAD acima: [connect.py](../../src/okto_nexus/adapters/inbound/cli/connect.py), [terminal_target.py](../../src/okto_nexus/adapters/inbound/cli/terminal_target.py), [work.py](../../src/okto_nexus/adapters/inbound/cli/work.py), [terminal_connection.py](../../src/okto_nexus/application/terminal_connection.py), [terminal_work.py](../../src/okto_nexus/application/terminal_work.py), [connection_setup.py](../../src/okto_nexus/application/connection_setup.py), [remote_terminal_setup.py](../../src/okto_nexus/application/remote_terminal_setup.py), [terminal-connect](../../docs/terminal-connect.md), [terminal-work](../../docs/terminal-work.md), [AgentConnectionsPanel](../../frontend/src/components/AgentConnectionsPanel.tsx), [connectionConfiguration](../../frontend/src/connectionConfiguration.ts), [connectionSessions](../../frontend/src/connectionSessions.ts), [runtimeApi](../../frontend/src/runtimeApi.ts).

Fontes Connector no HEAD acima, relativas à raiz daquele repositório: `cli/commands/connect.py` e `connect_reuse.py` (seleção antes de credenciais, revalidação), `configure.py` e `configure_local.py` (wizard, conflito, revisão/checkpoint), `connect_setup.py` (root remoto), `runtime.py` (roteamento R4 versus legado), `storage/state_store.py` (lock e snapshot); prefixo `src/okto_nexus_connector/`. Guias `docs/connection-configuration.md` e `docs/cli-reference.md` foram confrontados com handlers nos pontos citados. Leituras de código foram focais; nenhuma suposição de teste executado ou auditoria integral desses módulos.

O contrato cobre os três passos e o aceite documental UI-004: candidatos isolados e legado preservado; cinco intenções distintas; `--profile`/`--client`/flag proposta/JSON/incerteza rastreados a handlers existentes, com operação pelo terminal completa. UI-011–016 e UI-035–039 ainda devem implementar e provar os deltas. T-CLI-01, T-CLI-05, T-CLI-11 e T-CONN-01 permanecem **NOT_RUN nesta tarefa**: este arquivo é entrada para fixtures UI-005 e implementação, não resultado dessas jornadas. Não há serviço, provedor, autenticação pessoal, migração, alteração de produto, ledger ou Git produzido por esta tarefa.
