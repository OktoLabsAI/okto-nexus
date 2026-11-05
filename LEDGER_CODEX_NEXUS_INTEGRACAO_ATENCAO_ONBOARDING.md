# Ledger da implementação R3

Plano fixo: [PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md](PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md).
Detalhamento por tarefa, cenário, dependência e evidência: [ledger.json](plans/agent_ops/ledger.json).
Relatório: [implementation-report.md](plans/agent_ops/implementation-report.md).

## 2026-11-05 — Preparação autorizada

- Recuperada `origin/main` dos três repositórios, sem reset nem perda de mudanças locais. O plano fornecido permaneceu intacto.
- Nexus: base `c1e78e26fb2bd57ace3370417a2cb7529856b603`; branch `feature/v0.3.3`; versão `0.3.2 → 0.3.3`.
- Core: base `19c99f15b17ae994653ad9e190964229a0e296e8`; branch `feature/v0.0.14`; versão `0.0.13 → 0.0.14`.
- Connector: base `a3017d97b6a295cb2b46b9dd391b4c04ed121ee2`; branch `feature/v0.0.12`; versão `0.0.11 → 0.0.12`.
- Ambos os consumidores passam a fixar Core `0.0.14`. Metadados do frontend alinhados com Nexus.
- Criado ledger detalhado com todos os IDs originais. Nenhum marco funcional está concluído.
- Core e Connector empacotados; payloads Python comparados byte a byte com o código atual. Mesmo wheel Core nos dois consumidores.
- Validação: Nexus 10 testes; Core 3; Connector 19; instalação isolada Connector/Core 2. Todos passaram. Evidências XML em `plans/agent_ops/evidence/preparation-*.xml`.
- BASE-05 verificado: validação de cobertura preserva 59 tarefas, 132 cenários, 28 invariantes e 17 critérios de conclusão. Isso comprova rastreabilidade, não implementação dos requisitos.
- Preparação enviada: Nexus `ff6ee26`, Core `2093863`, Connector `7fd37c8`.

## 2026-11-05 — PR-00: baseline, contratos e correções iniciais

- Mapeados os caminhos canônicos de setup/Finish, pergunta/decisão, mensagens, inbox, handoffs/claims e arquivos MCP nos três repositórios.
- Criados [baseline.md](plans/agent_ops/baseline.md), [adr.md](plans/agent_ops/adr.md) e [evidência da validação](plans/agent_ops/evidence/pr00-validation.md).
- Corrigida a constante de compatibilidade do inventário para Core `0.0.14`, identificada no teste mais amplo após o bump; adicionada proteção contra divergência do pin.
- Corrigida orientação de autenticação do onboarding e preservado o scheme/origin do endereço. Documentação distingue configuração gerenciada de participante adicional; instruções legadas de stdio/CI/auth foram atualizadas.
- Runner frontend existente exposto por `npm test` e incluído na CI. Build do dashboard atualizado.
- **216 testes de baseline passaram**, além dos 34 da preparação. Startup descartável medido: HTTP disponível em 7,811s; shutdown canônico chegou a `DRAINED`. Sem inferência real.
- BASE-01…05 verificados no escopo de inventário/documentação/rastreabilidade. BASE-06 tem mapa e medição de processo implementados; tempo até sessão/resultado real permanece não executado. PR-00 entrega o mapa para PR-01, sem declarar aceite funcional de M1.
- Commit/push do baseline: Nexus `3df2e95`.

## 2026-11-05 — PR-01, primeira fatia: exclusão do Server

- Server adquire locks do SO para home e banco canônicos **antes** de bootstrap/migrações. Homes distintos que usam o mesmo banco também ficam protegidos.
- Heartbeat antigo não transfere ownership. Metadata possui geração; PID legado incerto/reutilizado não autoriza takeover nem recebe sinal.
- Testes incluem dois processos reais concorrentes, saída abrupta do dono, recuperação e preservação do shutdown canônico. Evidências: [pr01-locks.md](plans/agent_ops/evidence/pr01-locks.md).
- SVC-02 segue em progresso no contrato completo de instância; a camada de exclusão do Server está implementada/testada. Fachada, start/reuse, prontidão, supervisor e integração Connector continuam pendentes conforme o plano.
- Corrigida a normalização de newlines da entrada HTML e regenerado o artefato pelo build, após o check de whitespace detectar CRLF duplicado.

- Commit/push da exclusão: Nexus `825ab2f`.

## 2026-11-05 — PR-01, segunda fatia: prontidão e status passivo

- Identidade inclui componente, home/banco canônicos e usuário efetivo do SO. HTTP local de operador informa geração, versão ativa, armazenamento e admissão.
- `okto-nexus service status --json` correlaciona esses fatos com os locks, sem criar estado nem iniciar processos. Divergência de versão, identidade e transporte permanece explícita.
- **36 testes passaram**. Um Server real em home descartável confirmou a mesma geração pelo CLI/HTTP e chegou a `DRAINED`; depois, status retornou `stopped`. [Evidência e limites](plans/agent_ops/evidence/pr01-readiness.md).
- SVC-01/02/04 continuam em progresso no contrato completo; start/reuse, supervisor e Connector permanecem pendentes.

- Commit/push da prontidão: Nexus `b3168f18`.

## 2026-11-05 — PR-01, terceira fatia: start/reuse e controle local

- Fachada de aplicação para inspect/start/ensure_running/stop/restart, com contexto resolvido persistido e recibo de inicialização protegido por locks do SO.
- Server destacado usa o mesmo `serve`; requisições concorrentes reutilizam a inicialização. Timeout não mata nem relança. Stop/restart usam o shutdown canônico e exigem a geração observada.
- Teste real com três CLIs concorrentes confirmou um único PID/geração, continuidade após saída dos CLIs, reutilização, restart, recusa de stop obsoleto e parada `DRAINED`.
- A integração com supervisor instalado, logs, recuperação de lançamento interrompido e Connector continua pendente. Saída do processo CLI não foi confundida com campanha de logout/reboot ou fechamento de terminal real.
- Evidência: [pr01-start-stop.md](plans/agent_ops/evidence/pr01-start-stop.md).

- Commit/push de start/reuse e controle local: Nexus `333e1381`.

## 2026-11-05 — PR-02, primeira fatia: prontidão e parada do Connector

- Locks recusados fecham seus descritores. Status exige lock do SO, nascimento do processo e resposta IPC correlacionada à instância/geração/versão; IPC indisponível deixa de parecer ausência do daemon.
- `daemon status` em diretório ausente não cria estado. O entrypoint foreground respeita `--state-dir`; stop do lifecycle inclui a geração e verifica recibo durável do drain.
- A regressão identificou cancelamento duplo durante fechamento HTTP de uma tarefa de attachment. Corrigido para aguardar a limpeza, sem repetir cancelamento.
- **46 testes específicos e 75 de regressão passaram**. O wheel candidato do Connector foi reconstruído e seus 104 arquivos Python conferidos contra o fonte; manifest do Nexus atualizado.
- Evidências, qualificação do pacote e limites: [pr02-connector-readiness.md](plans/agent_ops/evidence/pr02-connector-readiness.md).
- SVC-11 permanece em progresso: supervisor por instância, contexto persistido, serialização completa de lançamento e campanha remota real continuam pendentes.
- Pacote isolado: **2 testes passaram**, incluindo start/reuse/stop do wheel instalado fora do checkout. Connector enviado em `97c5e13`, com limpeza de código legado inalcançável em `c4ad79d`.

- Commit/push da coordenação Nexus: `eb808757`.

## 2026-11-05 — PR-02, segunda fatia: definição compartilhada de serviço

- Core recebeu contrato puro para definição de tarefa de login Windows por instância e fingerprint da definição exportada pelo SO; sem efeitos de instalação no import.
- **13 testes passaram**, incluindo validação nativa do XML pelo Task Scheduler com `TASK_VALIDATE_ONLY` e ausência da tarefa verificada antes/depois.
- Corrigido conflito real de declaração UTF-8 via COM Unicode. Wheel Core atualizado nos dois consumidores; 130 arquivos Python comparados ao fonte, lock e manifest coordenados.
- Essa fatia verifica o contrato e a sintaxe. Registro efetivo, CAS, controles do supervisor e campanhas de login continuam pendentes. [Evidência](plans/agent_ops/evidence/pr02-core-service-definition.md).

## 2026-11-05 — PR-02, terceira fatia: supervisor Windows do Nexus

- Instalador por instância ligado à fachada/CLI, com proprietário, revisão nativa e contexto persistidos. Start usa a tarefa instalada; outra home não pode instalar supervisor sobre o mesmo banco.
- Stop registra supressão de recuperação antes do drain. Uninstall exige parada e preserva dados, contexto e credenciais. Definições alteradas e efeitos nativos sem confirmação permanecem explícitos.
- **159 testes passaram, com 2 skips POSIX**. Após a correção final de contenção de leitura/gravação de recibos no Windows, **56 testes afetados passaram**, incluindo três CLIs concorrentes e shutdown com geração correlacionada.
- A regressão também corrigiu leitura de metadata durante startup e liberação antecipada do lock pelo encerramento ASGI. O wheel final contém **411 arquivos Python idênticos ao fonte**.
- Validação nativa usou somente `TASK_VALIDATE_ONLY`; nenhuma tarefa pessoal foi instalada. Campanha efetiva de login/serviço, Connector, logs e os demais aceites continuam abertos. [Evidências e limites](plans/agent_ops/evidence/pr02-nexus-user-service.md).

## 2026-11-05 — PR-02, quarta fatia: supervisor e lançamento do Connector

- Recuperada novamente `origin/main` nos três repos; as branches de trabalho já contêm todas as bases remotas. Mudanças locais preservadas.
- Connector passou a serializar o lançamento entre CLIs e adquirir ownership antes de construir estado/vault/runtime. Contexto estável preserva referências; valores de proxy são resolvidos no lançamento sem serem gravados.
- Integração Windows por instância usa a definição compartilhada, recibos e revisão nativa. Start respeita o supervisor instalado; stop registra supressão antes do drain; uninstall preserva dados. Definições alheias/alteradas e respostas perdidas não autorizam sobrescrita ou novo daemon.
- **72 testes específicos**, **90 de regressão** e **2 de instalação isolada** passaram. Os 109 arquivos Python do wheel final correspondem ao fonte. Dependência Windows `pywin32` incluída no pacote; manifest do Nexus coordenado.
- Um teste inicial expôs lifetime incorreto de COM apesar do resumo positivo do pytest. A execução foi descartada; o adapter corrigido foi verificado em thread de trabalho com validação nativa sem registro.
- SVC-11 e PR-02 continuam em progresso. Controles restantes, recuperação/upgrade, campanhas reais e qualificação POSIX permanecem abertos. [Evidências e limites](plans/agent_ops/evidence/pr02-connector-user-service.md).
- Commit/push do Connector: `fc90370` em `feature/v0.0.12`.

## 2026-11-05 — PR-02, quinta fatia: logs passivos do Nexus

- Fachada e CLI oferecem `service logs --tail/--follow --json` sem bootstrap, inspeção de transporte ou startup. Home ausente continua ausente; contexto antigo quebrado não bloqueia a leitura.
- O mesmo foreground usado por execução direta, destacada e tarefa Windows grava códigos de lifecycle por geração após adquirir ownership. Rotação de 2 MiB, três backups e leitura limitada; mensagens de provedor, prompts e segredos não entram nesse formato.
- **49 testes passaram, com 2 skips POSIX**; **12 testes de logs passaram** após finalizar indicação de rotação e caso de falha de gravação. **13 testes passaram com o wheel instalado em venv limpa fora do checkout**, incluindo concorrência, reuso, restart, drain e logs das gerações reais.
- Os **412 arquivos Python** do wheel correspondem ao fonte. Ausência/falha de logs não comprova serviço parado nem trabalho concluído; Ctrl+C encerra apenas a observação.
- Os aceites completos de SVC e M1 continuam abertos. [Evidências, comandos e limites](plans/agent_ops/evidence/pr02-nexus-service-logs.md).

## 2026-11-05 — PR-02, sexta fatia: habilitação da tarefa selecionada

- Nexus e Connector expõem enable/disable sem iniciar, drenar ou cancelar a geração ativa. O entrypoint agendado recusa bootstrap quando a tarefa está desabilitada.
- Intento durável precede a mudança nativa. Repetir o mesmo comando reconcilia resposta perdida apenas se a diferença observada for a habilitação solicitada. Alterações de comando, privilégio, gatilho e outros campos permanecem preservadas para revisão.
- O Core fornece a comparação pura compartilhada; ambos os hosts mantêm ownership e efeitos do SO. O adapter COM do Nexus passou a inicializar/liberar recursos na thread da chamada.
- **12 testes do Core, 67 do Nexus e 62 do Connector passaram**. **90 testes coordenados passaram em venv limpa fora do checkout**, incluindo os processos destacados reais dos dois consumidores. Os 412/109/130 arquivos Python dos wheels correspondem aos fontes; Core e manifest coordenados.
- As mutações nativas desta fatia ainda foram testadas com backend simulado. Registro efetivo de tarefas, login/logout e demais aceites continuam pendentes. [Evidência e limites](plans/agent_ops/evidence/pr02-enablement.md).
- Commit/push dos contratos e do host remoto: Core `0490f88`; Connector `1f2f380`.
- Commit/push da integração e artefatos Nexus: `0cc52dc2`.

## Campanha nativa preparada

Preparado [roteiro revisável de tarefas temporárias](plans/agent_ops/campaigns/windows-user-service.md), com snapshot dos comandos, nomes, diretórios descartáveis e versões. A consulta nativa confirmou ausência das duas tarefas. **Registro/mutação ainda não executados**; autorização específica solicitada conforme o limite da seção 19. Essa pendência não bloqueia o restante da implementação.

## Próxima dependência

Avançar em PR-03/M1 com interação de trabalho, conversa, perguntas, decisões, resultados e reencontro pelo terminal sobre os contratos canônicos. As lacunas de PR-01/02 e a campanha de BASE-06 continuam rastreadas; os critérios de trabalho real local/remoto permanecem intactos.

## Aceites externos ainda não executados

Campanhas reais de provedor, login/logout/reboot, serviço do usuário e Herdr permanecem pendentes. O plano exige autorização específica para credenciais reais, inferência paga e mudanças na instalação pessoal. Preparar primeiro os percursos e artefatos revisáveis; solicitar apenas a autorização ou o ambiente necessário ao chegar a cada campanha.


## 2026-11-05 — PR-02, sétima fatia: diagnósticos passivos do Connector

- Recuperadas novamente as referências remotas de main nos três repos; todas já estão contidas nas respectivas branches feature.
- Status/logs/doctor padrão observam o diretório selecionado sem criar estado, lock, vault ou daemon. Probes explícitos respeitam a aprovação gravada do cofre.
- Status preserva starting/unknown/failed/degraded; IPC ou log inacessível não comprova ausência de trabalho. Saídas humana/JSON usam códigos estáveis.
- Logs possuem limite de leitura, retenção de registros parciais e indicação de rotação/truncamento. Corrigido conflito nativo de substituição de estado durante leitura no Windows com retry limitado, sem fallback destrutivo.
- **77 testes de fonte e 59 testes com wheel em venv limpa passaram**. Incluem CLI real em instância ausente e três starters concorrentes, reuso, restart e drain. Os **111 arquivos Python** do wheel correspondem ao fonte.
- Commit/push do Connector: `849f295`. Artefato/manifest e evidências coordenados no Nexus; Core permanece sem mudança nesta fatia.
- [Evidências e limites](plans/agent_ops/evidence/pr02-connector-passive.md). SVC-10/11, PR-02 e o plano integral continuam em progresso. A campanha nativa preparada segue aguardando autorização; nenhuma tarefa foi registrada.


## 2026-11-05 — PR-02, oitava fatia: recuperação antes do bootstrap

- Nexus e Connector oferecem `recover-start --expected-revision` para revogar explicitamente um lançamento destacado ainda pendente. O comando compara a revisão completa e a instância sob locks de lançamento e lifetime; não inicia substituto nem sinaliza PID.
- Filho atrasado revalida o recibo e sai antes do bootstrap. Dono ativo/incerto, tarefa instalada, revisão alterada e lançamento já admitido são preservados. Repetição após resposta perdida confirma o mesmo resultado sem nova gravação.
- **68 testes do Nexus e 81 do Connector passaram**; após os ajustes finais, **41 do Nexus e 11 de recuperação do Connector passaram**. **124 testes passaram nos wheels finais em venv isolada**, incluindo recuperação, três starters concorrentes, rejeição do filho antigo, reuso, restart e drain dos dois componentes.
- Os **412/111 arquivos Python** dos wheels Nexus/Connector correspondem aos fontes. Core permanece inalterado. Commit/push do Connector: `496c7e5`.
- [Evidências, comandos e limites](plans/agent_ops/evidence/pr02-launch-recovery.md). Upgrade controlado e reconciliação geral da definição/contexto continuam abertos; o subescopo não comprova recuperação de trabalho produtivo. A campanha nativa ainda aguarda a autorização solicitada.


## 2026-11-05 — PR-02, nona fatia: upgrade explícito de ambiente

- Main recuperada novamente nos três repositórios; as branches de trabalho já contêm os três heads remotos.
- Nexus e Connector oferecem upgrade-plan/upgrade-apply com revisão, preservação do contexto, drain canônico e retomada do mesmo plano após interrupção. O contexto pendente bloqueia novos starts; a ativação do destino ocorre por último.
- Troca de ação da tarefa preserva principal, gatilhos, políticas e enablement. Recibos, token e claim do banco ficam coordenados pelo fence; edição externa é preservada. Core commit/push: 57fa815.
- Testes: 17 Core; campanhas iniciais 125 Nexus/94 Connector; finais focadas 51 Nexus/42 Connector; 200 testes passaram nos wheels finais, sem skips. As duas campanhas reais trocam entre venvs descartáveis, preservam bytes do banco/ledger durante apply e terminam em DRAINED.
- Apply não inicia nem migra o runtime. O start explícito usa o caminho canônico e verifica o ambiente instalado. Rollback binário não é assumido seguro.
- Connector commit/push: `d82d941`; artefatos coordenados e hashes registrados nas evidências.
- [Evidências e limites](plans/agent_ops/evidence/pr02-upgrade.md). SVC-09 e PR-02 seguem IN_PROGRESS: atualização nativa real, versões históricas, migrações incompatíveis e trabalho produtivo não foram qualificados. A campanha nativa original continua aguardando a autorização já solicitada.

## 2026-11-05 — PR-03, primeira fatia: retomada do setup existente

- Recuperada novamente `origin/main` nos três repos; todas já estão contidas nas branches `feature/v0.3.3`, `feature/v0.0.12` e `feature/v0.0.14`.
- Nexus permite recuperar e conferir o recibo canônico de Finish pelo mesmo ID e conteúdo normalizado. Consulta exige autorização atual de operador e não reaplica configuração, vínculo ou grant.
- Connector registra o envio do Test antes do HTTP. Retomada consulta o recibo e observa o teste existente; cache perdido, Server antigo ou resultado incerto não causam outra chamada ao modelo. O assistente Server-hosted restaura a revisão salva antes de novas perguntas ou descoberta e rejeita argumentos conflitantes.
- **9 testes focados do Nexus, 32 do Connector e 65 com os wheels instalados fora dos checkouts passaram**, sem skips na rodada instalada. Integração usa cliente HTTP, handlers, autenticação e transação reais, com transporte e turno do harness simulados para injetar perda de resposta. Não houve inferência real.
- Os 415/114/130 arquivos Python dos wheels Nexus/Connector/Core correspondem byte a byte aos fontes. Wheel CI e manifest atualizados; Core permaneceu inalterado nesta fatia. Commit/push do Connector: `e365e9a`.
- [Evidências e limites](plans/agent_ops/evidence/pr03-setup-recovery.md). DX-17/19 e PR-03 estão em progresso; o `okto-nexus connect`, preset, criação unificada de identidade, interação de trabalho pelo terminal e campanhas produtivas continuam pendentes. Perda do cache foi injetada; restart real não foi qualificado nesta fatia. O plano R3 e M1 continuam incompletos.

## 2026-11-05 — PR-03, segunda fatia: entrada local pelo terminal

- `okto-nexus connect` usa a mesma resolução de contexto e fachada SVC para iniciar/reutilizar o Server local. `--plan` é passivo em relação ao serviço; a revisão e os checkpoints não secretos ficam em perfil local com gravação atômica e exclusão entre CLIs.
- Preset inicial resolve configuração runtime comum, decisões nativas e limites de 60 minutos/20 ações. Origem/revisão ficam no recibo de Finish existente. Aprovação exata precede verificação de instalação e teste com modelo; nenhum trabalho de projeto é enviado.
- Retomada consulta o mesmo setup; reconexão lê a configuração atual sem reaplicar defaults ou grants. Um vínculo canônico único do agente explicitamente escolhido pode ser reutilizado após conferir host/projeto. Edições posteriores de configuração e grants permanecem preservadas.
- **18 testes focados, 58 de serviço, 34 de regressão e 112 nos pacotes finais instalados passaram**. A campanha real do CLI iniciou/reutilizou a mesma geração de Server em home descartável e terminou em `DRAINED` após stop explícito. Setup/versionamento/modelo foram simulados nos testes de integração; não há aceite de provedor produtivo.
- Wheel Nexus: 419 arquivos Python idênticos aos fontes. Connector e Core permaneceram inalterados; hashes coordenados nas [evidências](plans/agent_ops/evidence/pr03-terminal-connect.md).
- DX-15…19/21 continuam em progresso. Criação unificada de identidade, preset completo de coordenação, início no login na revisão, participante/remote, trabalho/perguntas/decisões/resultados e campanhas produtivas ainda faltam. O plano integral e M1 não estão concluídos.

## 2026-11-05 — PR-03, terceira fatia: identidade na revisão do projeto

- Recuperadas novamente as três referências `origin/main`; as branches de trabalho já contêm seus commits. Versões/branches permanecem `0.3.3`, `0.0.12` e `0.0.14`.
- `connect` propõe ID persistente e nome a partir de harness/projeto, com papel generalista e permissões explícitas de coordenação. `--agent` reutiliza uma identidade; `--new-agent`/`--name` personalizam a proposta. Uma única revisão autoriza os efeitos concretos.
- Preview e Test não criam agente. Finish compartilha a rotina canônica de criação e sua transação com workspace, vínculo, políticas, chave e grant. Falha posterior desfaz os objetos novos; colisão de ID nunca adota outra identidade.
- O recibo existente recupera o mesmo resultado após perda de resposta/cache, sem outra chave ou grant. Chave permanente não é exportada ao perfil/Finish. Reconnect preserva alterações posteriores de nome, papel e permissões.
- Coordenação usa flags e limites atuais; nenhum poder administrativo ou de autoaprovação é concedido. Claim automático fica desabilitado para a identidade nova mesmo com default global ligado. Decisões nativas e limites de 60 minutos/20 ações permanecem.
- **14 testes focados passaram; 159 casos distintos foram validados nos wheels fora dos checkouts**: 158 passaram na rodada ampla e o único teste com comparação incorreta de presença passou no follow-up instalado. Os dois relatórios foram preservados, sem skips; nenhum fonte de produção ou wheel mudou entre as rodadas. Os 420/114/130 arquivos Python Nexus/Connector/Core correspondem byte a byte aos fontes. Connector e Core não mudaram nesta fatia.
- [Evidências e limites](plans/agent_ops/evidence/pr03-terminal-identity.md). Integração usa HTTP/autorização/transação reais e harness/modelo simulados; a regressão de processo termina em `DRAINED`. Trabalho/conversa/perguntas/decisões/resultados, remoto, login-start na revisão, participante e campanhas produtivas continuam pendentes. O plano integral e M1 seguem incompletos.

## 2026-11-05 — PR-03, quarta fatia: trabalho e decisões pelo terminal

- Recuperadas as três referências `origin/main`; todas já estão contidas nas branches de trabalho. Nexus permanece em `feature/v0.3.3`; Connector/Core não mudaram nesta fatia.
- `connect` interativo encaminha ao trabalho após a revisão. `work` permite solicitar, continuar a conversa, acompanhar, responder a perguntas/permissões, obter resultado e reencontrar a sessão. Controles usam as APIs canônicas, sem histórico local paralelo ou nova autoridade.
- IDs e hashes são gravados antes do envio; perda de resposta recupera a mesma operação/decisão. A consulta do intento correlaciona o turno inicial da solicitação atual, inclusive quando a abertura é reutilizada por pedidos distintos.
- Resultados, eventos, escopo, revisão, validade, destinatário e entrega nativa permanecem verificáveis no Server. Ctrl+C/EOF encerram a observação sem responder, interromper ou fechar a sessão; encerramento da sessão exige ação explícita.
- **29 testes focados, 44 de regressão e 2 de saída do observador passaram.** A rodada instalada ampla passou **99** testes e teve três falhas por ausência do schema na cópia dos fixtures. Após copiar o schema e corrigir EOF, **35** passaram no wheel final, incluindo os três casos. Relatórios separados preservam a sequência e não somam casos sobrepostos como cobertura distinta. Os 423/114/130 payloads Python correspondem aos fontes.
- [Evidências e limites](plans/agent_ops/evidence/pr03-terminal-work.md). Harness nativo simulado; HTTP, autorização, banco, admissão e dispatch reais. O gate `feature_hitl=false` foi preservado e sua recusa é apresentada; ativação na revisão e renovação de grants pelo terminal permanecem abertas, assim como remoto, login-start, participante e campanhas produtivas. DX-09/10/11/15/17/20 e PR-03 seguem em progresso; M1 e o plano integral continuam incompletos.

## 2026-11-05 — PR-03, quinta fatia: decisões nativas na revisão inicial

- A revisão do projeto inclui habilitação global de decisões nativas/HITL somente quando a opção ainda não foi definida. Explica o efeito sobre perguntas/permissões nativas e regras de aprovação de coordenação; não aprova pedidos nem concede administração ao agente.
- Test revalida sem aplicar. Finish grava a opção e seu recibo na mesma transação; rollback desfaz ambos. A configuração em memória só é atualizada após commit. Recuperação lê o valor persistido atual, inclusive uma desabilitação posterior, sem novo teste, grant ou reaplicação do preset.
- Políticas explícitas `false`, inclusive CLI/env iguais ao default, são preservadas. Contexto de serviço retém a origem das opções; argumentos congelados não transformam defaults em pins. Contextos antigos conservam overrides salvos, e sua origem ambígua não autoriza ativação automática.
- **12 testes focados passaram.** A regressão ampla teve **82 passes e uma falha**, que revelou perda de provenance no segundo bootstrap; o processo real passou após a correção. A campanha final instalada passou **267 testes, sem skips**, incluindo os contextos novo/antigo, restart, preservação da configuração, decisão nativa e recuperação de cache. Os 423/114/130 payloads Python correspondem aos fontes; Connector/Core não mudaram.
- [Evidências e limites](plans/agent_ops/evidence/pr03-terminal-policy.md). Native peer/modelo simulados; HTTP, autorização, transação e dispatch reais. Renovação de grants pelo terminal, remoto, início no login na revisão, participante e campanhas produtivas continuam abertos. M1 e o plano integral permanecem incompletos.
