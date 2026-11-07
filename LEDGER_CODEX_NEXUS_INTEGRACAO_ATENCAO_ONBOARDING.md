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

## 2026-11-05 — PR-03, sexta fatia: renovação explícita pelo terminal

- `work authorize` e `/authorize` revisam identidade, ações, prazo e orçamento antes de emitir pelo serviço canônico. Autorização disponível que cobre as ações do projeto evita outro grant. Nenhuma renovação ocorre por reconnect, observação ou restart.
- Emissão e recibo compartilham transação e ID estável. Concorrência, revisão obsoleta, falha tardia e resposta perdida não duplicam o grant. A recuperação preserva revogação posterior e funciona mesmo após alteração da configuração do projeto.
- Grants, leases e sessões existentes são preservados. Nova sessão escolhe autoridade produtiva com saldo; sessão expirada/esgotada não herda o novo grant. Inspeção, fechamento e novo trabalho permanecem ações explícitas.
- **18 testes focados**, mais **um caso de seleção e um de erro incerto**, passaram durante o desenvolvimento. A regressão instalada passou **247 testes** no candidato inicial; **30 testes passaram no wheel final**, incluindo os 20 casos de renovação. Rodadas e hashes são registrados separadamente, sem somar cobertura sobreposta. Os 424/114/130 payloads Python finais correspondem aos fontes; Connector/Core não mudaram.
- [Evidências e limites](plans/agent_ops/evidence/pr03-terminal-authorization.md). A fachada local está verificada com peer nativo sintético. Renovação pela topologia remota, login-start na revisão, participante e campanhas reais continuam abertas. M1 e o plano integral permanecem incompletos.

## 2026-11-05 — PR-03, sétima fatia: operador remoto e vínculo existente

- `operator login/status/logout` reutiliza a sessão humana do Server e guarda somente seu cookie em namespace próprio do cofre protegido. Perfil não secreto fixa origem, Server e usuário; não há senha em argv/arquivo nem credencial administrativa copiada ao Connector/harness.
- `connect --operator-profile` associa um vínculo já aprovado. A pasta local identifica o atalho do operador, sem substituir o caminho remoto. Reconnect/work recuperam a topologia antes do lifecycle local; indisponibilidade, sessão expirada ou mudança de identidade não iniciam Server substituto.
- Trabalho, recuperação de resposta perdida, renovação de grant e decisão nativa foram exercitados pelo HTTP autenticado humano, com autoridade canônica. Logout offline remove a sessão local e informa revogação remota não confirmada; redirecionamento entre origens não encaminha cookie.
- **24 testes iniciais e dois de decisão/cofre passaram.** O pacote instalado passou **167 testes**; **dois casos instalados adicionais** verificaram logout offline e o redirecionamento entre origens. Relatórios separados preservam a sobreposição. Os 427/114/130 payloads Python correspondem aos fontes; Connector/Core não mudaram.
- [Evidências e limites](plans/agent_ops/evidence/pr03-remote-operator.md). HTTP/Server reais com transporte adaptado, cofre em memória e peer nativo sintético. Nova identidade/setup remoto, aprovação de propostas do Connector, campanha real em dois hosts, cofre/TLS reais, login-start e participante continuam pendentes. M1 e o plano integral permanecem incompletos.

## 2026-11-05 — PR-03, oitava fatia: aprovação do Connector pelo terminal

- O operador inspeciona e decide a proposta canônica pelo CLI autenticado, com identidade, host, workspace, instalação, efeitos, revisão e prazo visíveis. A confirmação do participante não concede autoridade.
- Resposta perdida recupera o mesmo recibo sem outro POST. O serviço real do Connector reabre o estado persistido e aplica a intenção original: uma proposta, aprovação, binding e grant; nenhum cookie humano é transportado ao host.
- **30 testes do Server e 17 do Connector passaram nos fontes; 153 passaram na campanha instalada e 24 no pacote final após atualização dos metadados do README.** Os relatórios têm sobreposição. Os 429/114/130 arquivos Python correspondem aos fontes. O wheel de CI do Connector e seu hash foram atualizados; Core não mudou.
- DX-T32 verificado no contrato HTTP/persistência. DX-T40/45/46 seguem parciais; M1 real, novo agente remoto/setup unificado, serviço nativo, participante, ATN e OBS continuam pendentes. Escopo R3 preservado.
- Evidência: [pr03-terminal-binding.md](plans/agent_ops/evidence/pr03-terminal-binding.md).

## 2026-11-05 — PR-03, nona fatia: início no login na revisão local

- `connect --start-at-login` inclui usuário, instância, contexto e transição controlada no mesmo resumo do projeto. Recusar a opção mantém o uso sob demanda. Projeto existente pode revisar somente o startup.
- O setup canônico é concluído antes da integração do SO. Um checkpoint separado retoma instalação/prontidão sem repetir teste de modelo, Finish, binding ou grant; alterações de contexto e escolhas conflitantes são recusadas. Reconnect preserva desabilitação posterior.
- **8 testes novos e 30 regressões passaram nos fontes.** A primeira campanha instalada teve 150 passes e revelou uma recusa prematura durante leitura dos metadados de startup concorrente; corrigida com espera limitada sem novo start e três testes focados. **169 testes passaram no pacote final instalado**, incluindo criação de agente e processos reais. Os 431/114/130 arquivos Python correspondem aos fontes; Connector e Core não mudaram.
- Verificado o contrato local com SO/processo injetados. DX-T37 permanece parcial até integrar a opção ao wizard do Connector; login/logout/crash reais e M1 produtivo continuam pendentes. Escopo R3 preservado.
- Evidência: [pr03-login-start.md](plans/agent_ops/evidence/pr03-login-start.md).

## 2026-11-05 — PR-03, décima fatia: início no login no wizard do Connector

- `connect`/`configure` incluem a opção de login na mesma revisão local, com contexto completo e sem segredos. Recusar mantém o uso sob demanda; cancelar antes de Finish não altera tarefas.
- A intenção é persistida antes do drain/instalação/habilitação. Checkpoints recuperam falhas sem repetir registro/proposta nem criar tarefa duplicada; resposta nativa desconhecida exige inspeção. Retomada recusa escolhas conflitantes e preserva desabilitação posterior.
- A aprovação do operador no Nexus continua independente da escolha local. Sua conclusão em background preserva o checkpoint do host. A revisão humana não pode ser ocultada por `connect --json`.
- **74 testes passaram nos fontes; 152 do Connector e 104 do Nexus passaram nos artefatos instalados.** Os relatórios têm sobreposição; os 431/116/130 arquivos Python correspondem aos fontes. Pin e hash do Connector atualizados no Nexus; Core não mudou.
- **DX-T37 verificado no contrato de revisão/recusa em Windows, com efeitos nativos injetados.** Login/logout/crash/cofre reais, M1 produtivo e o restante do plano continuam abertos. Escopo R3 preservado.
- Evidência: [pr03-connector-login-start.md](plans/agent_ops/evidence/pr03-connector-login-start.md).

## 2026-11-05 — PR-03, décima primeira fatia: preset e política na aprovação remota

- Recuperadas as três referências `origin/main`; já estão contidas nas branches de trabalho. Versões permanecem `0.3.3`, `0.0.12` e `0.0.14`.
- O wizard padrão do Connector salva a origem do preset separada do JSON portátil. A revisão do operador inclui configuração, grant e o efeito global de decisões nativas. Política explícita desabilitada e mudanças concorrentes são preservadas; participante não autoriza esse efeito.
- Finish grava origem, configuração, grant, política e recibo na mesma transação. Atualização em memória ocorre após o commit. Falha nessa etapa produz resultado incerto recuperável pelo mesmo ID; o background do Connector retoma sem restaurar política desabilitada ou grant revogado posteriormente.
- **22 testes do Nexus e 37 do Connector passaram nos fontes; 127 do Nexus e 285 do Connector passaram nos wheels instalados.** Rodadas se sobrepõem. Os 431/116/130 arquivos Python correspondem byte a byte aos fontes; pin/hash do Connector atualizados. Core não mudou.
- Connector commit/push: `143ae449`. Contratos usam HTTP/SQLite reais com transporte, cofre e inventário sintéticos. Nova identidade remota, M1 produtivo, campanha nativa e demais frentes continuam pendentes. Plano fixo preservado.
- Evidência: [pr03-remote-preset.md](plans/agent_ops/evidence/pr03-remote-preset.md).

## 2026-11-05 — PR-03, décima segunda fatia: reconexão do projeto salvo no Connector

- Recuperadas as três referências `origin/main`: Nexus `c1e78e26`, Connector `a3017d9` e Core `19c99f1`. Todas já estão contidas nas branches de trabalho; nenhuma integração adicional foi necessária.
- `connect` na pasta configurada recupera Server, identidade e request ID pelo vínculo persistido. `--identity` reutiliza uma identidade importada; ambiguidades exigem seleção. A chave não é pedida nem gravada novamente na retomada normal.
- Para um pedido concluído, o CLI autentica a credencial atual e consulta a aprovação canônica antes de iniciar/reutilizar o daemon. Divergência de origem, pasta física, identidade, binding ou revisão local impede efeitos; revogação e desabilitação posteriores permanecem.
- Reconnect não repete probes, Finish, preset ou grants. Pedidos pendentes retomam seus checkpoints originais. A integração real com Nexus comprovou consultas GET, estado local intacto e uma única proposta/aprovação/conexão/grant.
- **67 testes do Connector e 8 do Nexus passaram nos fontes; 37 focados passaram após os ajustes finais. Nos pacotes instalados, passaram 180 do Connector e 75 do Nexus.** As rodadas se sobrepõem. Os 431/117/130 arquivos Python correspondem aos fontes; pin/hash do Connector atualizados.
- Connector commit/push: `09eb5f30`. Nexus produção e Core não mudaram. Nova identidade remota, M1 produtivo e demais frentes permanecem pendentes; plano fixo preservado.
- Evidência: [pr03-connector-reconnect.md](plans/agent_ops/evidence/pr03-connector-reconnect.md).

## 2026-11-05 — PR-03, décima terceira fatia: recomendação e revisão mínima no Connector

- `connect` recomenda a instalação única e pergunta somente quando há ambiguidade. Mantém o candidato completo do Core, inclusive Node/script do Pi, raízes e observações salvas; flags explícitas filtram o inventário local.
- Descoberta não executa o candidato. O probe fica no checkpoint após Finish; mudança de inventário exige nova revisão. Pasta atual, diretório do provedor e defaults aparecem com caminhos completos antes dos efeitos.
- Preferências avançadas são opcionais com `--customize`, pelo mesmo wizard e configuração. O resumo informa modelo, overrides, contexto, aprovação de ferramentas e limites de 60 minutos/20 ações. Cancelar não registra host, executa probe nem inicia daemon. A aprovação canônica continua no cliente do operador.
- **90 testes de fonte passaram, mais 2 casos do entrypoint. No pacote instalado, passaram 201 testes do Connector, 2 casos adicionais do entrypoint e 22 do Nexus**, sem skips. As rodadas têm sobreposição; wheel idêntico nas duas rodadas do Connector, com 431/117/130 payloads Python auditados.
- Connector commit/push: `b3167707`. Pin/hash coordenados no Nexus; produção Nexus e Core inalterados. Ruff dos fontes e unitários alterados, whitespace e ledger verificados; os 12 avisos F preexistentes no arquivo de auditoria legado são registrados na evidência.
- Nova identidade remota continua pendente. Foi solicitada preferência entre pareamento revisado e provisionamento prévio pelo operador; não houve resposta até este registro. M1 produtivo, campanha nativa e demais frentes continuam abertos; plano fixo preservado.
- Evidência: [pr03-connector-project-review.md](plans/agent_ops/evidence/pr03-connector-project-review.md).

## 2026-11-05 — PR-03, décima quarta fatia: introdução e identidade compartilhada no dashboard

- Recuperadas as três referências origin/main; todas continuam contidas nas branches feature já preparadas.
- A introdução lê o preset canônico, orienta projeto/harness pelo terminal e mantém a opção de cliente existente. Browser novo com identidade já configurada não reinicia onboarding; somente operator não conta como projeto.
- Connections mostra a origem e configuração salvas. Nome legível e papel usam a identidade existente; metadata tipada, chave, permissões, histórico, bindings e grants são preservados.
- **40 testes frontend, 32 integrações de fonte e 76 integrações instaladas passaram**, com sobreposição entre suítes. Build e Ruff passaram. Wheel limpo auditado: 431 arquivos Python e sete estáticos; Connector/Core mantêm 117/130 payloads e pins.
- Browser real com backend instalado verificou primeira visita, reuso, edição, teclado, temas, tela estreita e retry após 503 injetado. Conferência persistida confirmou uma identidade de projeto, um binding e um grant; retomada não repetiu setup. Harness sintético, sem inferência real.
- O primeiro teste HTTP revelou a rota de dashboard ausente, corrigida antes das suítes finais. A campanha de histórico foi ajustada para preservar todas as linhas anteriores permitindo notificações novas; produto e wheel permaneceram iguais.
- DX-12/18/19/21 e DX-T49 permanecem em progresso no aceite completo. RG-10 verificado para esta campanha. M1 produtivo, campanha nativa, participante, evolução do preset, identidade remota inicial, ATN e OBS continuam abertos; plano fixo preservado.
- Evidência: [pr03-project-dashboard.md](plans/agent_ops/evidence/pr03-project-dashboard.md).

## 2026-11-05 — PR-03, décima quinta fatia: diagnóstico passivo do projeto

- Recuperadas novamente as três `origin/main`; todas já estão contidas nas branches feature versionadas. Nexus permanece em `feature/v0.3.3`; Connector/Core não mudaram nesta fatia.
- `okto-nexus doctor` separa serviço, alcance do Server, autoridade atual do operador, identidade, binding, elegibilidade de abertura, sessão e resultado produtivo. Cada nível tem estado, motivo e próxima ação; login do provedor, cliente participante, MCP e cooperação não são inferidos.
- O padrão remoto lê somente metadados. `--check-server` permite GETs autenticados com limites explícitos; não inicia serviço/harness, executa probes, aplica configuração, emite grant ou envia trabalho. Falha anterior à criação do cliente HTTP não comprova resposta do Server.
- Criação de identidade pendente, inventário não observado e envio incerto permanecem desconhecidos. Grant revogado continua recusado. Resultado usa o recibo da solicitação salva; sessão pronta não vira conclusão produtiva, e diagnóstico não retoma nem reenvia operações.
- **52 testes de fonte e 82 testes instalados passaram. O wheel final passou 45 testes focados e três invocações reais da CLI fora do checkout.** As suítes se sobrepõem. O teste adicional de abertura foi corrigido para o contrato SUBMITTED com controle disponível; a falha original ficou preservada. Os 433/117/130 arquivos Python e sete assets do Nexus correspondem aos fontes.
- [Evidências e limites](plans/agent_ops/evidence/pr03-project-doctor.md). HTTP, autorização, persistência e recibos reais; peer nativo, ponte remota e cofre simulados. DX-07 e os cenários amplos permanecem em progresso; configuração participante, MCP/smoke, provedor real, serviço nativo e M1 completo continuam pendentes. O plano fixo não mudou.

## 2026-11-05 — PR-03, décima sexta fatia: evolução opcional do preset

- Recuperadas as três referências `origin/main`; todas continuam contidas nas branches versionadas de trabalho. Connector/Core não mudaram nesta fatia.
- `okto-nexus preset` apresenta diff canônico entre defaults anteriores, valores atuais e recomendação nova. Personalizações permanecem; aplicação exige revisão exata e usa o Test/Finish existente, sem nova infraestrutura de templates ou autoridade.
- O diff lista conexões, grants e aprovações de boot afetados, inclusive outras conexões da identidade quando muda a política global do agente. Concorrência ou efeitos ocultos recusam a aplicação; falha tardia desfaz a transação. Runtime desabilitado permanece sem teste/grant.
- Atualização local ativa declara o teste com modelo. Vínculo remoto existente usa operador humano e Finish do Server, sem probe remoto ou fallback local. Resposta perdida recupera o mesmo recibo; reconnect e replay de Finish antigo preservam configuração após a evolução.
- **148 testes passaram nos wheels instalados; oito casos de navegador foram ignorados por campanha desabilitada.** Follow-ups de cleanup (**4**) e reconnect/recibo antigo (**3**) passaram e se sobrepõem à rodada ampla. **Cinco casos do CLI executável** passaram. As falhas iniciais corrigidas e os relatórios separados estão preservados.
- Nexus: **436 arquivos Python e sete assets** correspondem aos fontes; Connector/Core mantêm seus pins e payloads. A recomendação publicada no código continua na revisão 1; revisões futuras 2/3 foram simuladas nos testes.
- [Evidências e limites](plans/agent_ops/evidence/pr03-preset-evolution.md). DX-T51 está verificado no contrato instalado declarado; DX-21/PR-03, M1 produtivo e o plano integral continuam em progresso. Campanhas reais de provedor, dois hosts, cofre/TLS e serviços nativos permanecem pendentes.

## 2026-11-05 — PR-04, primeira fatia: contrato de participante e formatos

- Core recebeu contrato puro separado do template gerenciado: cliente/versão, formato/revisão, origem aprovada, escopo de arquivo e referência de ambiente. Não aceita chave de agente como capacidade gerenciada nem altera os gates de qualificação nativa.
- JSON do Claude e TOML do Codex reutilizam editores com propriedade exata, CAS, backup e escrita atômica. Configuração alheia é preservada; remoção afeta só a entrada ainda pertencente à operação. Exportação genérica exige configuração manual; Pi não recebe adaptador HTTP inventado.
- **100 testes Core na fonte passaram. Nos pacotes instalados: 97 Core, 74 Connector e nove Nexus passaram.** Cinco casos Nexus inicialmente falharam na preparação do fixture por falta de SQL; passaram após copiar as migrações do wheel, sem mudar produção. Relatórios separados preservados.
- **Claude Code 2.1.317 e Codex CLI 0.166.0** leram os arquivos gerados em homes descartáveis; zero requisições MCP. O Claude manteve aprovação pendente. Leitura do formato não comprova credencial disponível, MCP negociado ou participação.
- Mesmo wheel Core com **131 arquivos Python conferidos** nos dois consumidores; Nexus/Connector mantêm seus payloads. Auditoria do import instalado não observou sockets, processos, threads ou leitura de arquivos fora do código. Pins continuam 0.0.14; nenhum pacote publicado.
- [Evidências e limites](plans/agent_ops/evidence/pr04-participant-contract.md). DX-01 verificado no contrato puro; DX-02/03 e PR-04 em progresso. `init`, integração de credencial/launcher, retomada local e cooperação autenticada seguem pendentes. O plano integral e M1 produtivo continuam incompletos.
- Commit/push coordenado: Core `7a58bd3`; Connector `7b2c3bf`.

## 2026-11-05 — PR-04: init de participante, proteção local e retomada

- `init --mode participant` e `connect --mode participant` compartilham seleção de Server, agente/workspace existentes, revisão e aplicação consentida. A consulta Bearer não cria identidade, grant, binding ou sessão nem altera o runtime existente.
- Entrada da chave existente por prompt oculto, stdin ou ambiente explicitamente escolhido; aprovação precede cofre e arquivo. Referência no cliente não contém o segredo. Cofre indisponível interrompe sem fallback plaintext.
- Checkpoints separados mantêm o mesmo `setup_run_id`; perda de confirmação recupera o arquivo exato sem duplicar alteração. Mudanças concorrentes são preservadas. Backups recebem ACL privada antes dos bytes; substituições conservam a ACL original verificada no Windows.
- **Fonte: 105 testes Core e 22 Nexus passaram. Instalados: 105 casos únicos Core, 80 Connector e 36 Nexus passaram**, incluindo recuperação após edição externa e regressão de connect gerenciado. Um teste documental precisou de duas correções no fixture temporário; os relatórios anteriores permanecem disponíveis.
- Wheels conferidos byte a byte: Nexus 441 arquivos Python e sete assets; Connector 117; Core 131. Mesmo novo Core nos dois consumidores, sem publicação de release. `origin/main` novamente recuperada e já contida nas três branches.
- [Evidências](plans/agent_ops/evidence/pr04-participant-init.md). DX-03/04/05/06 e PR-04 continuam em progresso. Credencial no launcher/GUI real, doctor de participante, MCP, cooperação, compensação/limpeza e M1 produtivo ainda não foram concluídos. O plano fixo permanece intacto.
- Core enviado em `5d31784`; candidato coordenado do Connector enviado em `7bdd0f5`.
- Finalização da entrega Nexus em 2026-11-06; evidências de validação mantêm a data original de 2026-11-05.

## 2026-11-06 — PR-04: doctor de participante e negociação MCP explícita

- `doctor --mode participant` inspeciona perfil/arquivo sem credencial, HTTP, processo ou escrita por padrão. Checks ativos são explícitos; ambiente ausente não recebe fallback silencioso para o cofre.
- `--check-server` autentica a identidade existente; `--check-mcp` inicializa o transporte e lista ferramentas com limites de origem, bytes, tempo e requisições. Não chama ferramentas, abre sessão de agente ou envia trabalho. Provas do doctor não são atribuídas ao harness externo.
- Campanha TCP com Server real preservou sessões de agente, bindings, grants e runtime. **32 testes de fonte e 55 instalados passaram.** Uma falha inicial com resposta já carregada em memória foi corrigida; relatório inicial preservado. CLI instalado confirmou perfil ausente sem criar diretório.
- Wheel Nexus com 444 arquivos Python e sete assets comparados byte a byte. Core/Connector inalterados neste marco. [Evidências](plans/agent_ops/evidence/pr04-participant-doctor.md).
- DX-04/07 e PR-04 continuam em progresso. Credencial no processo real do harness, comportamento MCP desse cliente, cofre real, cooperação, compensação e o plano integral permanecem pendentes.

## 2026-11-06 — PR-04: launcher de participante e ambiente dos clientes reais

- As três `origin/main` foram recuperadas e continuam contidas nas branches versionadas; Connector/Core não mudaram neste marco.
- `participant launch` revisa perfil autenticado, executável, projeto e configuração antes de iniciar o cliente no terminal. A chave do cofre vai somente no ambiente do filho; o shell pai permanece intacto. Codex exige `--no-daemon`; confiança do projeto e políticas nativas permanecem.
- Checkpoints anteriores ao spawn e recibos de término impedem relançamento automático após resposta incerta. `--new` solicita outra revisão explicitamente; PID e código de saída não comprovam prontidão.
- **19 testes de fonte e 74 testes instalados passaram.** A identificação inicial do adaptador Claude e o fixture de mudança de política foram corrigidos; o relatório da falha do fixture está preservado. Uma invocação instalada inicial apontou para nomes de testes inexistentes, corrigidos antes da suíte de 74 casos.
- **Quatro casos com Claude Code 2.1.317 e Codex 0.166.0**, em homes temporários e modos de protocolo, verificaram referência presente/ausente usando os helpers instalados. Somente a referência presente autenticou MCP no responder sintético. Mesmo sem credencial, o processo retornou zero; o produto mantém a prova de MCP separada. Nenhum prompt, turno de modelo ou chamada de ferramenta foi enviado.
- Wheel Nexus com 447 arquivos Python e sete assets conferidos byte a byte. [Evidências e limites](plans/agent_ops/evidence/pr04-participant-launch.md). DX-04/05/06/07 e PR-04 seguem em progresso; cofre real integrado ao cliente, GUI/TUI interativo, cooperação canônica, compensação, serviços nativos e M1 produtivo continuam pendentes. Plano fixo preservado.

## 2026-11-06 — PR-04: remoção local e compensação de participante

- `participant remove` revisa e remove somente a entrada de cliente ainda pertencente ao setup e sua credencial isolada no cofre. Não faz HTTP nem apaga identidade, altera validade da chave, runtime, bindings ou grants no Server.
- A aprovação registra aposentadoria do perfil antes dos efeitos; checkpoints de arquivo/cofre retomam perdas de resposta sem restaurar backup antigo ou reescrever edições posteriores confirmadas. Init/connect/launch recusam reativação; doctor permanece passivo no perfil aposentado. `--keep-config` deixa arquivos explicitamente intactos.
- **24 testes de fonte e um caso adicional no cofre real do Windows passaram.** A rodada instalada passou **108 regressões**, seguida de **quatro casos sobrepostos no wheel final** após melhorar a orientação de erro do cofre. Dois relatórios iniciais foram preservados: ajuste da expectativa de round-trip TOML e correção real da preservação de `AUTO_INHERITED` na DACL protegida.
- Credential Manager foi exercitado com chaves de fixture em namespaces temporários; remoção e ausência posterior foram confirmadas. Nenhuma credencial pessoal foi lida, substituída ou rotacionada. Testes de outros backends foram injetados.
- Wheel final: 449 arquivos Python e sete assets comparados byte a byte. Connector/Core não mudaram neste marco. [Evidências e limites](plans/agent_ops/evidence/pr04-participant-removal.md).
- DX-03/04/05/06/07 e PR-04 seguem em progresso no aceite integral. Cooperação canônica, cadeia completa cofre/cliente interativo, GUI/TUI, outras plataformas, campanhas nativas de serviço e M1/M2 produtivos permanecem pendentes. Plano fixo preservado.

## 2026-11-06 — PR-05: base interna de recibos de coordenação

- Recuperadas novamente as três `origin/main`; todas já estão contidas nas branches versionadas. Connector/Core não mudaram neste marco.
- Schema 159 e porta de persistência guardam chave por instalação/ator/workspace/operação/request ID, hash semântico sem credenciais e referências mínimas de recurso/aprovação. A transação pertence ao caso de uso; não há commit separado nem lock apenas em memória.
- A referência de aprovação e seu prazo são preservados na resolução. Janela fixa de 30 dias, tombstone após remoção da mensagem e limpeza em lotes pelo retention/admin prune existentes. Expiração não decide nem apaga a aprovação original.
- **73 testes de fonte e 104 testes instalados passaram**, incluindo oito conexões concorrentes, encerramento de processos antes/depois do commit, rollback, upgrade 158→159, retenção e recuperação de cache sem regrant. Uma invocação real do CLI instalado confirmou schema/janela em home temporário.
- A checagem de arquitetura encontrou um import preexistente de SQLite na aplicação; a correção mantém o resultado de setup já confirmado quando a atualização do cache falha. O teste agora examina o pacote importado também fora do checkout. Relatórios iniciais preservados.
- Wheel final: 451 arquivos Python, sete assets e 159 SQLs conferidos byte a byte. [Evidências e limites](plans/agent_ops/evidence/pr05-coordination-receipts.md).
- **Este marco não habilita retry público.** As composições de teste exercitam os repositórios; integração dos casos de uso de mensagem/handoff/aprovação, autenticação e visibilidade atuais, outbox/contabilização, checkpoint/recovery da CLI, recusa fora da janela, espera e cooperação seguem pendentes. DX-10, PR-05 e o plano integral permanecem em progresso; os alvos fixos não mudaram.

## 2026-11-06 — PR-05: criação e recuperação canônicas de coordenação

- `message_create` e `handoff_create` recebem `client_request_id` opcional; repetição preserva a referência original, inclusive aprovação pendente. Consulta autenticada `coordination_request_get` devolve somente metadados e não cria trabalho nem heartbeat.
- Revalidação de chave/capability/permissões e escopo/proveniência antes do replay. Objeto, inbox/outbox, eventos e recibo compartilham a transação canônica; repetição não cria outra execução nem consumo.
- Resultado e evento de aprovação são confirmados junto com o recurso. Schema 160 acrescenta revisão monotônica para impedir execução ou compensação atrasada sob outra decisão. A proteção adicional de arquivamento é defesa do repositório; o endpoint já recusava arquivar execução em andamento.
- **74 testes principais de fonte, 14 de remetentes gerenciados e quatro testes finais de corrida passaram** (suítes com sobreposição). **225 testes de comportamento instalados passaram** fora do checkout. O wheel final após compactação de descrições passou mais **53 testes instalados**, com uma medição opcional de tokenizer não executada; aplicação/domínio são idênticos ao wheel da regressão. Upgrades 158/159→160 preservam dados; falhas de processo e cortes de transação recuperam o mesmo pedido.
- Superfície: custo exato de 542 caracteres de DX-10 registrado no ledger de crescimento existente. Baseline, divisor e limiar de 40% preservados; descrições com até 200 caracteres e redução ajustada de 40,1298%.
- Wheel com 453 arquivos Python, sete assets e 160 SQLs conferidos byte a byte. Relatórios iniciais preservados, com redação apenas de duas ocorrências de chaves sintéticas de fixture. [Evidências e limites](plans/agent_ops/evidence/pr05-coordination-creation.md).
- Connector/Core não mudaram neste marco. CLI com checkpoint durável/recovery/recusa após janela, espera correlacionada e cooperação continuam pendentes. Peers nativos sintéticos não qualificam M1 produtivo. DX-10, PR-05 e plano integral seguem em progresso, sem alteração dos alvos fixos.

## 2026-11-06 — PR-05: CLI de coordenação, retomada durável e espera passiva

- Entregues `message send`, `handoff create`, `handoff wait` e `request inspect`, com perfil participante existente, ator autenticado e MCP canônico direto. Sessão/contexto explícitos são preservados; a CLI não abre sessão por comando nem converte roteamento.
- Checkpoint privado antes da transmissão, recuperação do mesmo ID após perda de resposta/morte real do processo, janela original local/Server de 30 dias e recusa de replay fora do contrato. Conteúdo, resultado e segredos não são persistidos nesse checkpoint; `--new-request` exige intenção explícita de novo trabalho.
- Espera correlacionada usa cursor antes do snapshot, long-poll limitado e releitura canônica. `VERIFYING`, entrega/leitura de mensagem e idle nativo não indicam conclusão. Timeout/Ctrl+C não cancelam nem reenviam trabalho; falha de observação preserva os IDs da criação já confirmada.
- Corrigida a atualização de `last_seen_at` na autenticação HTTP de leituras passivas, não capturada nos testes anteriores de serviço. Autenticação fresca ignora cache positivo; revogação continua recusada no transporte e na transação. Também corrigidos validação sob Python `-O`, valores canônicos de visibilidade e proteção do diretório do perfil antes de ler credencial.
- **614 testes distintos passaram em wheels instalados**, com uma medição opcional de tokenizer não executada. As duas falhas iniciais da regressão instalada eram expectativas antigas de HTTP 200 para chave revogada; agora verificam HTTP 401 e conservam teste independente de contexto obsoleto na transação. Relatórios iniciais preservados, com seis ocorrências de chaves sintéticas redigidas.
- Wheel final: **457 arquivos Python, sete assets e 160 SQLs**, conferidos byte a byte; SHA-256 `1bd3360cc050cba59fb440aa04c55e8726e25a01d769278ebe977b60b39e944e`. Somente a proteção do perfil na CLI difere do wheel da regressão ampla; o final passou os 42 casos afetados/de fronteira e as correções de expectativa. Dependências compatíveis. A superfície preserva baseline/divisor/limiar e redução ajustada de 40,1298%.
- **DX-09/10/11 implementados**, com subcontratos instalados verificados; DX-T15…25 verificados no escopo declarado. A aceitação combinada com clientes qualificados, cooperação DX-08, campanhas nativas e M1/M2 produtivo continuam pendentes. PR-05 e plano integral seguem em progresso, sem mover os alvos. Connector/Core não mudaram neste marco.
- [Evidências e limites](plans/agent_ops/evidence/pr05-coordination-cli.md).

## 2026-11-06 — PR-03/PR-04: smoke opcional de cooperação

- Entregue `participant smoke exchange|handoff|observe|status`, com revisão da mensagem dirigida e consentimento separado para handoff. A prova vem da resposta canônica correlacionada e do claim/resultado do destinatário; strings do modelo e `NEXUS_CONNECTION_OK` não qualificam cooperação.
- Leitura passiva observa respostas já consumidas sem alterar inbox/presença. Recibos autenticados e publicações nativas bem-sucedidas têm proveniência verificada; publicações falhas/interrompidas e autores legados não confirmados não passam.
- IDs/checkpoints duráveis preservam a tentativa após perda de resposta ou morte real do processo. Consentimento anterior sem checkpoint permite apenas inspeção, sem reiniciar janela. Corrigidos também PASS histórico apresentado como atual e perda da indicação de possível efeito após revogação. Falha comprovada antes do primeiro envio mantém recusa sem efeito.
- Status e planos retidos permanecem locais e passivos, inclusive com lock ocupado. Doctor mostra histórico como UNKNOWN; uma observação atual sem prova revalidada também retorna UNKNOWN e conserva o histórico.
- **440 testes distintos instalados passaram**, com uma campanha manual A/B não executada. Relatórios iniciais e correções preservados; a contagem substitui casos revalidados, sem somar reruns. O wheel final contém **460 arquivos Python, sete assets e 160 SQLs** idênticos ao fonte; SHA-256 `bb9143f2181993d93ff78dba9d6a6536d9a2f20de3b602997e048474ce43307d`. Dependências compatíveis; Ruff passou nos arquivos alterados.
- **DX-08 implementado**, com subcontratos verificados entre identidades sintéticas. Clientes/provedores reais, M1/M2 produtivo, campanhas nativas e plano integral continuam pendentes. PR-03/04/05 seguem em progresso; os IDs e o hash do plano fixo não mudaram. Connector/Core não foram alterados.
- [Evidências, falhas corrigidas e limites](plans/agent_ops/evidence/pr04-cooperation.md).

## 2026-11-06 — PR-06: backend da central de atenção

- Entregues os doze tipos iniciais, projeção em lote, API de operador com filtros/paginação/total coerentes, visto/adiado compartilhado e SSE de invalidação. GET não decide nem altera o trabalho.
- Migração 161 aditiva: preferências e âncoras de episódios estáveis. Arquivamento remove ações nativas; expiração compara instantes; falhas de leitura retornam erro sanitizado. Reset e aposentadoria preservam a semântica das âncoras.
- **462 testes distintos instalados passaram**, com 0 skips. Wheel conferido byte a byte: 470 Python, 7 assets, 161 SQLs; SHA-256 `8642d7ed8b3fe51a7cd9bb72f9f79452c638b9aea124ef7e29ea6c1403418824`. Relatórios iniciais e limites preservados.
- ATN-02/03/04 implementados com subcontratos verificados. **PR-06 continua em progresso**: bloqueios de autoridade ainda cobrem apenas handoffs gerenciados, e aprovações não nativas não estão projetadas. ATN-01/05 seguem em progresso; PR-07 UI/browser permanece pendente. M1–M4 e plano integral não foram declarados concluídos. Connector/Core não mudaram.
- [Contrato](docs/attention.md) e [evidências](plans/agent_ops/evidence/pr06-attention.md).

O wheel de entrega remove apenas uma linha vazia final; equivalência sintática, demais payloads e instalação conferidos em `pr06-attention-release-scope.json`.

## 2026-11-06 — PR-06: aprovações, resultados e autoridade

- Aprovações genéricas entram na projeção; a decisão canônica aceita revisão opcional e recusa formulário obsoleto após falha/retomada.
- Resultados manuais/MCP e nativos do mesmo handoff compartilham identidade por claim. Migração 162 preserva visto/adiado, histórico e registros legados com data de atualização ausente; migração 161 intacta.
- Bloqueios de mensagens, handoffs e decisões nativas revalidam autoridade atual em lote, incluindo origem, destinatário, relay e notificações. Inspeção canônica alcança handoffs antigos, executor e recibos de limpeza além dos limites das listas; leitura de limpeza funciona com execução desabilitada sem habilitar mutações.
- **718 casos comportamentais distintos instalados passaram; zero skips**, mais uma observação explícita de limitação. Wheel final: 477 módulos Python, 7 recursos estáticos e 162 migrações; fontes e bytes instalados conferidos. Falha inicial real em timestamp legado corrigida; 43 casos requalificam os dois payloads alterados no wheel final.
- AT-01/02/16 verificados no backend. PR-06/ATN-01/AT-08 continuam em progresso: off→on→off somente da flag global ainda reutiliza episódio/visto/adiado; falta geração persistida da política efetivamente aplicada. O teste que documenta isso não conta como aceite de recorrência.
- PR-07/UI/browser, campanhas reais de cliente/provedor/serviço e aceite integral R3 seguem pendentes. Connector/Core permanecem nas branches preparadas, sem alterações neste marco.
- Evidências e limites: [pr06-attention-completion.md](plans/agent_ops/evidence/pr06-attention-completion.md). Plano e conjuntos fixos de IDs preservados.

## 2026-11-06 — PR-06: episódios da política efetiva

- Política global efetiva de harness/HITL tem geração durável, publicada pelo Server com lock válido após resolução de CLI/env/overrides.
- Alterações em memória só se aplicam após commit. Rollback, no-op, restart sem mudança e reset preservam as regras de geração; GET/MCP bootstrap não publicam.
- Recorrência na mesma hora recebe outro episódio, sem herdar visto/adiado. Mudança irrelevante não renova bloqueio independente de grant.
- **403 casos instalados distintos passaram**, sem skips. Um teste preexistente de exclusão de SQLite aberto falha no Windows também no wheel anterior; foi registrado e desmarcado na suíte instalada, sem contar como aprovação.
- Migração 163 aditiva; 161/162 intactas. ATN-01 implementado, recorrência backend verificada; AT-08/PR-06 seguem com reconciliação/browser pendentes. PR-07/UI e demais campanhas R3 continuam abertos.
- Evidência: [política efetiva](plans/agent_ops/evidence/pr06-attention-effective-policy.md). Core e Connector não mudaram neste marco.

## 2026-11-06 — PR-07: central de atenção integrada

- Menu, badge por workspace, filtros e grupos Needs action/Watch ligados à projeção canônica. Visto/adiado permanecem preferências; inspeções abrem os controles existentes.
- Cliente serializa leituras/escritas, agrupa SSE e reconcilia por prazo, reconnect e conflitos. Falhas retêm snapshot desatualizado; negação/desativação limpa cards, contadores e inspeção.
- Confirmação e fences de revisão/claim preservados; rascunhos sobrevivem a refresh e falha transitória. Sucesso confirmado limpa o guard de mudanças; revisões novas exigem nova revisão do formulário.
- **100 testes frontend e 10 contratos do wheel instalado passaram**, sem falhas/erros/skips. Relatórios dirigidos repetem casos e não são somados. Build passou com aviso já conhecido de chunk grande.
- Chrome com Server/SQLite reais e peers sintéticos validou visto/adiado, conflito concorrente 409, verificação claim_epoch, pergunta/permissão/recusa/expiração de 120 segundos, rede/reconnect, desativação, foco, temas e largura de 390 px. Injeções 503/403 e HTML de teste estão distinguidas dos fluxos canônicos reais.
- Wheel final: 478 Python, 163 migrações, 7 assets com conjuntos/bytes idênticos ao fonte/instalado; HTTP serviu os mesmos assets. Instâncias descartáveis encerradas pelo drain canônico.
- PR-06/07 e ATN-05…08 IMPLEMENTED, com subcontratos verificados; AC-04 verificado. OBS, campanhas reais pendentes e aceite integral R3 continuam abertos. Core/Connector não mudaram neste marco.
- Evidências e limites: [pr07-attention-ui.md](plans/agent_ops/evidence/pr07-attention-ui.md).

## 2026-11-06 — PR-08: ingestão externa com autoridade restrita

- OBS-01…04 implementados e verificados no Server: fonte aprovada pelo operador, instâncias independentes, geração emitida pelo Server, permissões explícitas e credenciais de publicação restritas. Migração 164 aditiva; histórico anterior preservado.
- Ingestão valida autoridade atual antes de replay; seq/hash, TTL, quota e eventos ficam na mesma transação. Revogação, rotação e reset não restauram tokens antigos. Leitura/expiração não alteram presença, capacidade ou trabalho canônico.
- OBS inicia desligado. Settings oferece toggle e 15 limites, com budgets por fonte/agente/instalação, lote atômico de até 100 e fila limitada. Retenção existente preserva fences e não repõe quota após redução de taxa.
- Qualificação: **525 testes verdes únicos de código**, **14 testes instalados** (repetições identificadas), **49 verificações HTTP reais**, TypeScript/Vite/Ruff e inspeção de Settings em Chrome, claro/escuro/390 px. Toggle/limite sobreviveram a reload; TTL inválido bloqueou salvar; valores do ambiente descartável restaurados.
- Wheel Nexus `0.3.3`: `85a882cf1ee71ff953e3ce79a25216a1092d0b3a7e314b72527749267e07c130`; **486 Python, 164 migrations e 7 static** com conjuntos/bytes iguais entre origem, wheel e instalação. Server descartável encerrado por shutdown canônico `DRAINED`.
- Diagnósticos iniciais preservados: fixture HTTP sem `preset_id`, helper de build com `-I` e ajustes de seletores/esperas/viewport da automação visual. Nenhum foi contado como teste aprovado. Falhas de disco/commit são injetadas, não uma campanha de encher disco físico.
- Evidências e limites: [pr08-observations.md](plans/agent_ops/evidence/pr08-observations.md), [manifesto](plans/agent_ops/evidence/pr08-observations-tests.json) e [contrato de uso](docs/external-observations.md).
- PR-09 (Herdr real/helper), PR-10 (atenção externa/regressão conjunta) e campanhas reais já nomeadas de M1/M2/serviços continuam abertos. Core/Connector sem alterações neste milestone. Escopo R3 e todos os IDs permanecem fixos.

## 2026-11-06 — PR-09: observador e helper em qualificação

- Implementados `observe herdr bind|run|status`, vínculo explícito, identidade de criação do processo local, transporte só de metadados, journal com exclusão e helper de publicação restrita. A recuperação preserva a incerteza acumulada e nunca troca o reporte pendente por outro conteúdo.
- **316 testes distintos de origem passaram**. Revisão independente cobriu transporte, identidade, persistência, CLI e recuperação; diagnósticos iniciais permanecem no manifesto.
- Herdr Windows x64 **0.9.5/protocolo 22/schema 1**, pacote oficial com checksum e schema instalado retidos. A sessão descartável confirmou working/blocked/idle/done, referência estável de conclusão, renomeação e preservação do done após leitura. O observador fez 53 chamadas permitidas, sem leitura de terminal nem controle.
- O processo observado e os hooks são sintéticos, explicitamente identificados. Isso qualifica a integração com Herdr real, sem alegar execução de provedor/cliente nativo. Wrappers, remote e outras plataformas não são aceitos como identidade comprovada.
- Qualificação com Nexus instalado, casos restantes de troca/desconexão e commit/push PR-09 estão em andamento. Core/Connector não mudaram; PR-10 e os demais aceites integrais R3 continuam abertos.
- [Evidências de progresso](plans/agent_ops/evidence/pr09-herdr-progress.md) e [manifesto inicial](plans/agent_ops/evidence/pr09-herdr/initial-manifest.json).

## 2026-11-06 — PR-09: observador Herdr e helper qualificados

- Entregues `observe herdr bind|run|status`, vínculo explícito com revisão, identidade Windows por processo/criação/imagem/host, transporte só de metadados e helper restrito. Journal persiste intenção/seq antes de cada envio e mantém incerteza até recibo válido; retry histórico explícito não precisa do executável Herdr.
- **318 testes de implementação, dois de regressão CLI e 321 testes instalados passaram**; reruns anteriores não são somados. Wheel final `fe597e0e5a7256d6c3328382d4a046706cba3cc37f4e15e286afad54eab2d29d`: **668 arquivos** conferidos. V2 altera somente o transporte CLI Herdr; os 667 demais arquivos são iguais aos do Server real mantido para a campanha.
- Herdr Windows **0.9.5/protocolo 22/schema 1** real, schema/ZIP/executável com hashes retidos. Processo observado e hooks são sintéticos, explicitamente distintos de OpenAI Codex ou inferência. Campanhas reais cobrem working/blocked/idle/done, referências estáveis, renomeação, dois namespaces com mesmo pane ID, movimentação, substituição e stop/restart.
- A campanha instalada auditou **143 leituras** permitidas; a de estado, 53; a de namespaces, 34. Nenhuma leu terminal ou controlou agente. **147 tabelas canônicas permaneceram idênticas**; conclusão repetida emitiu um único evento observacional; startup/reassociação não inventaram conclusão. TTL expirou para stale/unknown.
- O teste real de move encontrou recusa sem invalidação persistente; V2 corrigiu `HERDR_TARGET_CHANGED` e revalidou o fluxo. Relatórios iniciais permanecem. Quatro strings de credencial sintética em IDs de testes foram redigidas com hashes originais preservados; bearer temporário não foi coletado.
- As duas Herdr foram encerradas canonicamente, com saída dos processos próprios confirmada. Nexus terminou `DRAINED`, sem recursos/erros, e seu PID saiu; a sondagem TCP não conectou. Nenhum serviço pessoal ou provedor foi usado.
- **PR-09 IMPLEMENTED; OBS-05…10 VERIFIED no escopo Windows/local declarado.** PR-10, campanhas reais pendentes de M1/M2/serviços e aceite integral R3 continuam abertos. Core/Connector sem alterações; hash do plano e conjuntos fixos de IDs preservados.
- [Evidências e limites](plans/agent_ops/evidence/pr09-herdr.md), [manifesto de 142 artefatos](plans/agent_ops/evidence/pr09-herdr/artifact-manifest.json) e [uso do observador](docs/herdr-observer.md).

## 2026-11-06 — PR-10: projeção externa em implementação

- PR-09 commitado e enviado em `add07318`, com 142 artefatos conferidos também no índice do Git. Connector e Core permanecem sincronizados, sem mudanças nesse marco.
- OBS-11 em implementação: ocorrências externas, resumo completo por agente, inspeção de instância e interface com origem, atualidade e limitação explícitas. Os testes HTTP novos ainda não foram executados.
- OBS-12 em revisão do mecanismo de evidência/autorização para correlação. Instâncias existentes continuam separadas; `canonical_session_ref=null` não comprova a precedência exigida para instâncias correlacionadas.
- PR-10 e o aceite integral R3 permanecem abertos. O bootstrap de identidade remota e as campanhas reais de M1/M2/serviço continuam pendentes; nenhuma evidência sintética foi promovida a qualificação real.

## 2026-11-06 — PR-10: reconciliação documental de DX-13

- **DX-13 VERIFIED por reuso já demonstrado em PR-03/PR-04:** dashboard e terminal usam Connections/Test/Finish e seus recibos canônicos; `automatic_reply` continua normalizado, sem opção independente; adicionar/reconectar participante externo preserva runtime, bindings, endpoints, grants e políticas do agente existente.
- Relatórios instalados retidos confirmam os casos pertinentes: terminal connect **112 passes**; preset evolution **148 passes e 8 skips de browser**; participante Nexus **36 passes**; Connector **80 passes**. Há sobreposição entre suítes; estes números não são somados. A campanha de navegador existente mostrou a configuração gerenciada salva, sem reaplicar Finish ao abrir/fechar Connections.
- Esta revisão documental não executou testes/campanhas nem alterou produção. As provas usam efeitos nativos/provider sintéticos e, no participante inicial, vault sintético; não qualificam provider real nem o wheel atual de PR-10. PR-03/PR-04, M1/M2, bootstrap remoto, campanhas nativas e aceite integral R3 mantêm seus status e limites anteriores.
- Somente a tarefa DX-13 e uma entrada de histórico foram reconciliadas no JSON. Plano, demais tarefas e inventários permanecem intactos. [Referências, casos e limites](plans/agent_ops/evidence/pr10-dx13-reconciliation.md).

## 2026-11-07 — PR-10: qualificação de observações externas

OBS-11 implementado: três tipos de acompanhamento, inspeção exata e resumo completo por agente. Há 340 casos fonte atuais e 121 casos frontend aprovados; as campanhas instaladas iniciais de 158 e 110 casos se sobrepõem. O browser real confirmou as transições com dados sintéticos, mantendo 146 tabelas canônicas inalteradas. A consulta única passou nas 24 amostras finais com 4.096 instâncias (atenção completa: mediana 3,22 s; máximo 3,73 s), preservando o limite de cinco segundos. A regressão instalada ampliada da wheel V4 está em execução. Resultados anteriores e limites foram preservados em [evidências PR-10](plans/agent_ops/evidence/pr10-external.md).

OBS-12 possui somente o contrato puro de evidência/digest/fences (91 casos); associação persistida e precedência canônica continuam pendentes. PR-10, campanhas reais e R3 permanecem em andamento, com o inventário e o hash do plano preservados.

## 2026-11-07 — PR-10: reconciliação documental de DX-07 e SVC-12

- O subcampo `participant_client_validation` de DX-07 passa de NOT_STARTED para **IMPLEMENTED**, limitado ao caminho existente de validação do participante. O XML histórico do doctor registra **55 passes**, sem falhas/erros/skips, incluindo inspeção passiva, drift separado de autenticação, revogação e MCP TCP sem inferir participação ou trabalho.
- SVC-12 passa a distinguir upgrades controlados e diagnósticos já implementados das campanhas nativas ainda abertas. O XML histórico de upgrades registra **200 passes**, sem falhas/erros/skips, incluindo substituição real entre ambientes instalados descartáveis; efeitos de Task Scheduler foram injetados. Os dois totais não são somados nem qualificam o wheel atual.
- DX-07 e SVC-12 continuam **IN_PROGRESS**. Clientes/provedores reais, contrato diagnóstico entre hosts, login/logout/crash/credenciais e demais campanhas nativas mantêm seus limites. Nenhum marco, M1/M2, autorização ou inventário foi alterado; DX-13 e o progresso de OBS-11/12 foram preservados.
- Revisão documental com leitura nominal dos XMLs, comparação semântica do JSON e checker de escopo; nenhum teste ou serviço foi executado. [Evidências e limites](plans/agent_ops/evidence/pr10-ledger-reconciliation.md).

## 2026-11-07 — PR-10a: OBS-11 qualificado

A wheel V4 qualificou 292 casos: 291 passaram na regressão ampliada e um teste antigo de migração, que dependia do checkout, passou após correção em execução focal. O relatório original com a falha permanece retido. Os relatórios instalados dos candidatos somam 431 identidades distintas, sem somar reexecuções. Os 341 casos fonte atuais, 121 casos frontend, browser real com dados sintéticos e 24/24 amostras de volume sustentam OBS-11 como VERIFIED. As evidências preservam as falhas iniciais, candidatos substituídos e limites da campanha. Manifesto e verificador vinculam os bytes retidos aos arquivos staged antes do commit.

OBS-12, PR-10 completo, campanhas reais e regressão conjunta R3 continuam pendentes. OB-19 permanece NOT_RUN e OB-24 IN_PROGRESS. Não houve qualificação nova de provider, cliente MCP real ou serviço nativo. Detalhes: [PR-10](plans/agent_ops/evidence/pr10-external.md).

## 2026-11-07 — DX-07/DX-14: diagnósticos do Connector

Commit e push `12d806f955aea84327dd3a33011016d0283ecc18` em `feature/v0.0.12`. O formato comum opt-in passou nos mesmos 93 casos fonte e instalados, com dependências sintéticas e 119 arquivos de pacote verificados byte a byte. A saída padrão e os exit codes foram preservados; o probe explícito passou a validar também a identidade do Server. O lado Nexus tem 75 casos fonte aprovados e ainda aguarda qualificação instalada. DX-07/DX-14 e R3 continuam em andamento. [Evidência](plans/agent_ops/evidence/pr10-diagnostics-connector.md).


2026-11-07 — OBS-12: armazenamento CAS/tombstones, prova nativa autorizada, API e projeção/UI de precedência canônica implementados. Revisão corrigiu recusa após await, limites de admissão, datas de recibos corrompidas e tipos de revisão. Wheel instalada, browser e medição de carga ainda em qualificação; OBS-12 e PR-10 permanecem IN_PROGRESS. Plano fixo preservado.


## 2026-11-07 — PR-10b: precedência canônica e diagnóstico comum qualificados

OBS-12 e OB-19 passam a VERIFIED no escopo Windows/local declarado. Associação explícita de operador, CAS/tombstones, revisão de autoridade e projeção passiva preservam os fatos canônicos e mantêm o sinal externo separado. A prova de processo/Core desta fatia usa dados sintéticos; isso não qualifica associação real com provedor.

A V1 passou em 736 casos instalados. A V2 altera somente duas consultas de atenção e passou nos 237 casos afetados, com 20 identidades novas: são 756 casos distintos entre candidatos, dos quais 519 permanecem qualificados na V1 inalterada. Os 681 arquivos finais correspondem ao fonte/build/wheel/instalação; 679 arquivos e os sete assets são idênticos à V1. Frontend: 130 passes. Browser real V1: oito checkpoints, 13 tabelas canônicas preservadas e encerramento confirmado.

A medição inicial preserva 86/90 sucessos e quatro recusas pelo orçamento de cinco segundos. Após restringir o preload às ocorrências pertinentes, o mesmo driver registrou 90/90 sucessos e 0 recusas na V2, sem retries nem alteração do prazo. Resultados são separados por candidato; não constituem SLO geral. [Evidências, falhas iniciais e limites](plans/agent_ops/evidence/pr10-correlation.md).

Diagnóstico comum v1 verificado: Nexus 75 casos instalados; Connector 93 já publicados em `12d806f955aea84327dd3a33011016d0283ecc18`. São os mesmos casos fonte de cada repo, sem soma duplicada. O contrato compartilhado é declarativo; DX-07/DX-14 completos e campanhas reais entre hosts continuam em andamento. Core permanece sem alterações neste milestone.

PR-10 integral e R3 continuam IN_PROGRESS. Bootstrap remoto, M1/M2 produtivos, campanhas de serviço/provedor/cliente e regressão conjunta permanecem abertos. Plano e inventários fixos preservados.


## 2026-11-07 — PR-03: bootstrap remoto e revisão no mesmo setup

O fluxo de identidade/workspace remoto foi implementado e qualificado: revisão humana, bootstrap parcial com chave exibida uma única vez, handoff autenticado, filhos R4, decisão canônica e Finish único. Revisões locais mantêm o bootstrap e o histórico, exigem nova confirmação material e recuperam um Finish anterior confirmado durante a revisão. Credencial atual, CAS e revogação continuam obrigatórios; nenhuma credencial administrativa chega ao host.

Pacotes não editáveis fora dos checkouts: **Nexus 187/187 e Connector 276/276 passaram**. Os 690 arquivos Nexus e 123 Connector correspondem ao fonte/build/wheel/instalação. Core 0.0.14 inalterado. Os seis cenários conjuntos usam TCP/WSS reais e fixtures explícitas para instalação/provedor/cofre; não qualificam M1/M2 produtivos ou implantação em dois hosts. Falhas iniciais e retestes permanecem preservados, sem soma duplicada.

Connector commit/push: `7091ef2ebbf4b47ee41e38ec6b6df8c56e583f3c`. O plano e os conjuntos fixos de 59 tarefas, 132 cenários, 28 invariantes e 17 critérios permanecem iguais. PR-03, PR-10 integral e R3 continuam IN_PROGRESS; serviços nativos, provedores/clientes reais, renovação remota e regressão conjunta integral continuam pendentes. [Evidências e limites](plans/agent_ops/evidence/pr03-remote-bootstrap.md).

Pacote Nexus final: remoção apenas de duas quebras vazias no EOF, com AST equivalente; 35 testes instalados de contrato/HTTP/guards passaram novamente, sem somá-los aos 187 casos únicos. A evidência anterior e a tentativa de build sem setuptools foram preservadas.


## 2026-11-07 — PR-03: renovação remota e reconexão após troca de chave

Quatro cenários conjuntos qualificaram renovação por esgotamento/expiração, resposta perdida, rotação explícita, reconexão concluída e revogação com HTTP/WebSocket, IPC TCP e DaemonApp reais. O harness/provedor é sintético. Bootstrap e Finish históricos permanecem imutáveis; setup pendente mantém o epoch original. Emissão pendente conserva incerteza durante falha de acesso, enquanto falha de leitura de recibo confirmado não reabre a emissão.

Pacotes instalados: **Nexus 66/66 e Connector 233/233**, sem somar retestes. Core inalterado. Connector commit/push `fb3fff473ff246adcffa9e91573ac85f7a394170`. Plano e inventário fixos preservados; M1/M2 produtivos, serviços/cofres nativos, TLS/dois hosts e R3 integral permanecem abertos. [Evidências e limites](plans/agent_ops/evidence/pr03-remote-renewal.md).

## 2026-11-07 — Guia público de participante no dashboard

Onboarding e agente existente agora compartilham comandos públicos de review/apply/launch/doctor, com origem e workspace explícitos. Snippets que embutiam a chave foram removidos; a entrega one-shot permanece separada. Copiar o guia não cria identidade, gira credencial ou altera runtime.

Passaram 138 testes de frontend e typecheck/build; 22 checkpoints no navegador usaram o wheel instalado com 690 arquivos conferidos. Nos dois Servers, as 34 comparações de estado permaneceram iguais, inclusive hashes brutos de agentes. As requisições capturadas foram GET; console sem erros/avisos. Layout de 390 px, tema escuro, clipboard, foco e onboarding vazio foram conferidos. Browser encerrado e ambos Servers DRAINED com PIDs finalizados.

Somente subescopos de DX-03/04/05/12 e DX-T01/03/09/11/35 foram verificados. Os status globais e DX-02 cofre real→cliente permanecem iguais; M1/M2/R3 seguem abertos. Connector/Core sem alterações. [Evidências e limites](plans/agent_ops/evidence/pr04-participant-guide/milestone.md).

## 2026-11-07 — Dependência CI atual e matriz de fechamento

O pin CI do Connector foi corrigido para o wheel publicado a8cf1810, com 123 arquivos iguais à fonte. Venv limpa com MCP 1.30.0 passou no pip check e nos 8 testes instalados pelo runner CI, sem alterações de inputs. O ambiente histórico de browser tinha MCP 1.29.1 abaixo do mínimo declarado; não é usado como prova de resolução de dependências.

Matriz finita dos17 critérios e11 RG registrada; ainda há verificações conjuntas, compatibilidade e revisão de evidências que podem avançar sem autorização. A proposta atualizada de duas tarefas temporárias Windows está preparada e aguardando resposta; nenhuma tarefa foi registrada. Aceites reais e plano integral continuam abertos. [Evidências e proposta](plans/agent_ops/evidence/r3-qualification-readiness/milestone.md).


## 2026-11-07 — R3: contratos conjuntos instalados

71 casos únicos passaram: 9 de coordenação/entrega mista, 6 de isolamento idle, 17 de modos de sessão e 39 de recuperação selecionada. Dez casos novos e correção mínima da geração da fixture remota; aplicações e wheels inalterados. RG-01/02/03/04/11 verificados no escopo canônico Windows com peers sintéticos. RG-05/06 permanecem em progresso; import audit Core cobre 131 módulos com limites explícitos. Não há promoção de M1/M2 ou aceite global. Evidências e tentativas iniciais: `plans/agent_ops/evidence/r3-joint-contracts/milestone.md` e manifesto adjacente. Compatibilidade, rastreabilidade/revisão pública final e campanhas reais continuam pendentes.


## 2026-11-07 — R3: revisão e redação de artefatos públicos

Revisados 1.822 arquivos públicos dos três repos. Dois valores foram redigidos em relatórios históricos: uma chave UAT e um ticket sintético de fixture. Hashes antes/depois, fonte e falhas originais permanecem documentados; 35 ocorrências restantes são parâmetros inválidos de testes. A segunda varredura confirmou essa classificação. AC-10 permanece aberto: a validade/revogação da chave UAT e commits anteriores não foram alterados ou verificados, e a varredura tem limites declarados. Aplicações/wheels e configurações pessoais inalterados. Evidência: `plans/agent_ops/evidence/r3-public-artifact-review/milestone.md`.


## 2026-11-07 — R3: versões, imports e pacotes

Quatro pares instalados qualificados: versões Core alinhadas aceitas; dois pares cruzados recusados com VERSION_INCOMPATIBLE antes de efeitos. 131 módulos Core importados sob guards, nove controles negativos e stdout bruto retido; fronteiras atuais sem violação. Pacotes completos: Nexus690/Connector123/Core165 arquivos, sem recurso-fonte omitido. RG06/07/08 e AC07 verificados para o snapshot Windows atual. Documentação de compatibilidade e proposta Windows vigente atualizadas. Rastreabilidade vinculada sem somar reruns; RG09, AC09/10 e campanhas reais continuam abertos. Revisão tarefa/cenário a tarefa/cenário segue somente leitura. Evidência: `plans/agent_ops/evidence/r3-compatibility-boundaries/milestone.md`.


## 2026-11-07 — R3: reconciliação literal e lacuna SVC07

Revisados os59 IDs sem novas execuções: BASE/SVC18, DX21, ATN/OBS20. Corrigidos195campos com acentos corrompidos, comprovando apenas reparo de codificação; checker passa a exigir texto literal do plano. ATN/OBS e14contratosDX verificados; seteDX implementados aguardam qualificação real. Contratos puros SVC reconciliados sem transformar adapter injetado em serviço real. AC06/09 e AC10 no escopo dos artefatos entregues verificados; risco histórico UAT/Git continua registrado fora desse aceite, sem novo requisito de reescrita/revogação. Lacuna concreta SVC07 (drain antes de contenção e decisão explícita de força) continua aberta; T06/T12/T13 em qualificação segura. M1/M2/R3 não concluídos. Evidência: `plans/agent_ops/evidence/r3-task-reconciliation/milestone.md`.

## 2026-11-07 — R3: falhas de startup e interrupção da espera

Corrigido o diagnóstico público de porta ocupada: `PORT_IN_USE` no log limitado,
sem texto bruto da exceção nem troca de endpoint/banco. **21 testes instalados
passaram** em snapshot isolado: sete novos e14 reutilizados. Retidos os resultados
anteriores, incluindo6pass/1falha real. T06/T12/T13 verificados: porta realmente
ocupada, falhas reais de configuração/migração/storage e Ctrl+C injetado na espera
do connect com o mesmo processo vivo, depois READY/DRAINED. Nenhum serviço nativo,
provedor ou cofre pessoal utilizado. SVC07 e campanhas reais seguem pendentes.
Evidência: `plans/agent_ops/evidence/r3-service-boundaries/milestone.md`.

## 2026-11-07 — SVC-07: contrato cooperativo do Core

Core publicado em 3cdba87: fence de novas operações, observação passiva e composição de owners do mesmo journal. Foram verificados 217 casos únicos no pacote instalado; tentativas e falhas de preparação permanecem retidas. A mesma wheel 1407014e… foi atualizada nos dois consumidores. Nexus e Connector seguem em validação integrada, sem declarar SVC-07 ou M1 completos. A proposta M1 usará Codex CLI, conta já autenticada e limite total de 200 mil tokens informado pelo usuário; execução real e acesso a credenciais ainda não ocorreram. Evidência: ../okto-nexus-connector-core/docs/evidence/cooperative-drain/milestone.md.

## 2026-11-07 — SVC-07: drenagem cooperativa nos três componentes

Core publicado em `3cdba87` e Connector em `ef8e267`. Nexus qualificado com247
casos únicos de drenagem/autoridade/serviço e45 de isolamento/recuperação:
**292 casos instalados aprovados**. Rodadas fonte e instalada não são somadas.
As15 falhas iniciais instaladas foram de preparação/fixture; seus relatórios
permanecem retidos, seguidos de62 retestes aprovados, sem mudança da wheel.
Drain mantém decisões, leases, resultados e ACKs admitidos; novas admissões
ficam bloqueadas. Timeout permanece pendente e força exige geração atual/prazo
vencido. SVC-07 implementado, com campanhas reais ainda abertas.

Os28 invariantes foram reconciliados como contratos/arquitetura, sem promover
M1/M2. SVC-02 fecha a lacuna de porta ocupada e RG-09 fecha o ambiente herdado
dos45 casos. Propostas atuais usam wheels qualificadas; conta já autenticada
e200 mil tokens definem a proposta M1, mas o teto rígido segue sem garantia
técnica e a opção de monitoramento ainda aguarda resposta. Nenhum serviço
nativo/provedor/credencial real foi executado neste milestone.

Evidências: `plans/agent_ops/evidence/r3-cooperative-drain/milestone.md`,
`plans/agent_ops/evidence/r3-invariant-reconciliation/accepted.json` e
`plans/agent_ops/evidence/r3-campaign-proposals/milestone.md`.

## 2026-11-07 — documentação vigente e contratos de recuperação

Corrigidos oito documentos dos três repos: fluxos já entregues deixaram de ser
descritos como futuros; referência Connector confere com75 parsers atuais;
API Core documenta drain cooperativo. Dez helps Nexus passaram e29 recursos
JSON Core conferem com a wheel. Core docs publicado em `f9a5c3b`, Connector em
`55a14a6`; produto e wheels inalterados.

Dois casos físicos existentes passaram nas wheels atuais, em perfis isolados:
Nexus e Connector com start concorrente, reuso, restart e drain, sem serviço
nativo/provedor. Matriz explícita fecha AC-05/08/15 dentro dos contratos;16DX e
SVC-T26/T28 passam a VERIFIED por provas específicas já retidas. Não se somam
nodes de relatórios sobrepostos nem se apresentam mocks como Task Scheduler.
T23/T24 ganham testes focais separados de restart real; sua aceitação ainda não
é antecipada. M1/M2 e campanhas reais permanecem abertos.

Evidência: `plans/agent_ops/evidence/r3-contract-closure/milestone.md`.

## 2026-11-07 — cenários DX restantes

Reconciliação literal dos21 cenários DX restantes:16 contratos verificados,
cinco campanhas reais mantidas pendentes (T34/T38/T39/T40/T43). O caso existente
de inbox alheia passou nos três parâmetros instalados (`count/peek/history`),
com as mesmas wheels, ambiente isolado e inputs inalterados. Os92 pares de
relatório/node da matriz são referências sobrepostas, não novos testes.
T50 verifica honestidade de aceite; não declara M1 concluído. Não houve produto,
credencial pessoal, provedor ou Task Scheduler alterado neste milestone.
Evidência: `plans/agent_ops/evidence/r3-dx-final-contracts/milestone.md`.

## 2026-11-07 — reinício e ownership de processos

Quatro novos casos passaram no código-fonte e nos pacotes instalados atuais.
SVC-T22/T23/T24 e RG-05 foram verificados no escopo literal: reinício pendente
preserva o filho real, claim e slot; queda/retorno do Server preserva vínculos,
limites e grants e não repete trabalho. A prova usa PID canônico, nascimento,
geração e saída do processo real. O filho fecha com exit0 antes da liberação.
As tentativas de preparação e o PASS invalidado por PID do redirector estão
preservados; não contam como cobertura nova. Não houve mudança de produto,
inferência real ou Task Scheduler. M1 e campanhas de plataforma seguem abertos.
Evidência: `plans/agent_ops/evidence/r3-service-restart-contracts/qualification.json`.

## 2026-11-07 — critérios de aceite contratuais

AC-02/12/16/17 verificados pela composição entre frentes, exclusividade de
instâncias, identidade/preset/limites e preservação da configuração. Auditoria
conferiu74 pares relatório/node existentes e82 entradas públicas estáveis;
não são74 testes novos. AC-01/03/11/13/14 continuam abertos com lacunas literais
específicas. A qualificação de reinício03b3e801 complementa AC14; suspensão real
permanece pendente. Dois clientes MCP podem ter qualificação direta sem provedor
se essa capacidade for comprovada; initialize sozinho não basta. Nenhum código
de produto, inferência ou registro nativo mudou neste milestone.
Evidência: `plans/agent_ops/evidence/r3-acceptance-contracts/milestone.md`.

## 2026-11-07 — dois clientes MCP existentes

AC-03 verificado: MCP Inspector0.21.2 programático e FastMCP2.14.7 abriram
sessões úteis, trocaram mensagem/resposta dirigida com correlação canônica e
reconectaram sem duplicar identidades ou sessões. Um caso passou na fonte e
no Server instalado; são duas execuções do mesmo caso. A tentativa inicial
com oráculo de DTO incorreto foi preservada. Não houve provedor, modelo,
credencial pessoal, adaptador nativo novo ou alteração de produto.
O handoff separadamente consentido de DX08 e a campanha M1 continuam abertos.
Evidência: `plans/agent_ops/evidence/r3-two-existing-mcp-clients/qualification.json`.

## 2026-11-07 — smoke de cooperação com dois clientes

DX-08 verificado com Inspector/FastMCP e TerminalCooperation/CooperationFiles
reais: troca dirigida, consentimento separado do handoff, claim/epoch e resultado
canônicos. Consentimento errado/antecipado não cria efeitos. Reconstituir a
fachada recupera os mesmos IDs sem novas chamadas produtivas. Dois casos passaram
na fonte e nos pacotes instalados: um novo e o caso AC03 requalificado porque o
helper compartilhado mudou. Não houve produto, modelo, credencial pessoal ou
serviço nativo alterado. M1 e launcher/cofre de DX04 continuam separados.
Evidência: `plans/agent_ops/evidence/r3-two-mcp-cooperation/qualification.json`.
