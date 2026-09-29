# Handoff explícito — Server, Core e Connector

**Este documento fixa trabalho coordenado; não afirma que as interfaces R4 já foram implementadas.** O Server é o destinatário principal. O agente do Server não edita os outros repositórios sem atribuição/autorização; abre os pedidos abaixo com IDs e fixtures, e mantém gates externos visíveis.

## 1. Baselines e situação

| Produto | Fonte conferida | O que pode ser usado agora | O que não presumir |
|---|---|---|---|
| Nexus | feature/v0.2.0, 7ed52c22865a92c3768bc32508ed9e35dc5efdc3 | Domínio/HTTP/CLI/migrações existentes | Executor remoto R4, remoção stdio ou integração Core já feitos |
| Core | 0.2.10.dev0, 1560d314ed2b478515dcbbe533436d7d0b027b09 | create_runtime, catálogo, availability v2, installation_ref/resolve_installation, Journal/ledger/controles | NXL R4 publicado, attach qualificado, E2 multi-host ou mesmo hash de wheel sem verificá-lo |
| Connector | 0.4.0.dev0, 87b8fd2e3e403cb6a70a1ce265618e29c7a6b86c | CLI/daemon/HTTP/WSS e composição parcial em desenvolvimento | CN5 encerrado, remote open completo, decisões persistentes ou inventário/UI remoto qualificados |

O CN5 documenta Q01 proposta redigida/namespace, Q02 producer de decisão, Q03 rotação de attach e Q04 publicador interrompido. O plano Server incorpora essas invariantes. Não herdará flags de prontidão do Connector sem fatos de negociação e teste do caminho real.

## 2. Entregas obrigatórias do Core

### CORE-R4-01 — Bundle executável R4

**Entrada:** delta em `contratos/nxl-r4-delta.json`, documento 02, schemas/fixtures de planejamento. **Saída:** wheel com revisão R4, schema fechado por verbo, codecs/reducers e hash vetores; R3 preservado para histórico.

Passos: copiar para uma pasta de especificação do Core; implementar geração na fonte única; declarar novos ACKs de attach/reconcile e lease correlacionada; owner obrigatório; controlar targeting de adapter; executar casos positivos/negativos contra consumidores sintéticos dos dois aplicativos. Não instalar schemas do diretório de planejamento como runtime autoral do Server.

**Aceite:** payload extra ou permissão autodeclarada falha antes do efeito; r3 não é aceito como r4 pelo mesmo major; enum deriva do registry; todos os eventos/receipts históricos usados na migração continuam lidos pelo decoder apropriado. Não re-hashear registros persistidos.

### CORE-R4-02 — Estabilizar helpers públicos usados pelos hosts

**Entrada:** APIs existentes em discovery, harness_config, Journal e composition. **Saída:** documentação/exports/testes de consumidor instalado que fixem as assinaturas realmente suportadas.

Não acrescentar um daemon ao Core. O objetivo é garantir discovery sem dummy runtime, preservação de InstallationCandidate completo, renderização HTTP direta e leitura finita de histórico. Caso um helper continue provisório, publicar a fachada pública mínima no próprio Core e adaptar os hosts uma vez. Não permitir imports `native.*` nos aplicativos.

**Aceite:** catálogo/discovery/evaluation/resolver funcionam no wheel sem classe privada; a operação de listar não exige iniciar provider, obter credencial ou criar candidato falso.

### CORE-R4-03 — Projeções de targeting e fatos de capacidade

**Entrada:** capacidades já implementadas nos adaptadores e testes atuais. **Saída:** campos públicos que permitam ao Server saber se controle requer native turn ID ou usa run sem ID, sem array específico por harness no Server.

Não ampliar capacidades por descrição. Pi com steering de próxima fronteira não vira IMMEDIATE. Attach segue não qualificado. Alterar schema R4 e fixtures quando o campo cruza wire. `execute_work` depende de tool path e aprovação, não só protocol support.

**Aceite:** Server não importa provider nem codifica regras próprias para construir target; consumidor passa somente combinações demonstradas, Core revalida no efeito.

### CORE-R4-04 — Artefato e compatibilidade por hash

Gerar wheel/sdist com dependências fixadas e manifest R4; manter package version independente de wire revision. Publicar **localmente para os agentes**, sem PyPI/release automático. Registrar hash completo, não fragmento de README. Consumidores instalam o mesmo arquivo, não dois builds diferentes com o mesmo número.

**Aceite:** import -I, conformance, catálogo v1, availability v2, duas instalações iguais resolvidas inequivocamente, testes históricos e novas fixtures passam na camada declarada. Provider/SO/multi-host continuam gates separados.

## 3. Entregas obrigatórias do Connector

### CON-R4-01 — Concluir CN5 sem enfraquecer domínio

Executar o pacote CN5 inteiro. Proposta operacional íntegra e display redigido são separados; namespace chega até SessionKey; producers sobrevivem ao waiter; attach novo é agendado após término do antigo; reconexão recria publicador necessário. Cada Q fecha com reprodução na entrada efetiva, não populando estado privado para evitar o problema.

### CON-R4-02 — Um único dispatcher de efeitos

Atualizar `RuntimeManager.start/submit/stop` usados pela CLI: registrar client_intent_id localmente antes de POST, chamar Server resolve/admit e consultar resultado. **Não chamar Core diretamente nessa trilha depois de pedir operação canônica.** A chamada Core fica na entrada de executor do dispatcher WSS R4 ou no shutdown proprietário interno, que não é uma nova intenção de trabalho do usuário.

Implementar remote runtime.open com refs de realização e lease inicial; preservar operation_id/scope/hash. Não anunciar G2 enquanto o verbo permanecer UNSUPPORTED. Corpo raw executable/argv/env recebido da rede é recusado.

### CON-R4-03 — Consumir DTOs HTTP R4 completos

Atualizar MeInfo/BindingProposal/IntentResolution/DecisionView/receipts e revisão em headers. Resposta de approval não é bool para aplicar nativo localmente; application operation chega pelo dispatcher único. Receipts usam endpoint próprio ou NXL receipt, nunca POST de execução com payload diferente.

Migrar clientes com validação explícita de revisão. Não manter fallback de permissões para simulação no código produtivo. GET por client_intent_id recupera operação quando response se perde.

### CON-R4-04 — Lanes e lease com ACK efetivo

Adotar binding.attached/reconcile.accepted, request tokens e source connection generation. Lane só pronta após ACK da mesma epoch. Rotação usa provider novo e agenda substituto sem emprestar sua revision ao resultado anterior. Guardar expiração do ticket e renovar automaticamente dentro do escopo.

Lease request captura t0 antes de enviar; reply serial é aplicada uma vez; replay não reancora prazo. Core recebe renovação/revocation por API própria antes de tornar a sessão produtiva. Nenhum `allowed.update()` local amplia grant.

### CON-R4-05 — Snapshot e resolução no mesmo inventário

Produzir `ExecutorInventorySnapshot` com candidato completo, disponibilidade Core e hash de todas as evidências. Publicar por HTTP na origem aprovada sob ticket próprio; UI remota devolve ref/revisão/escopo. Resolver somente pelo Core no executor original; não reconstruir Pi por executable isolado ou validar revisão de `[candidate]` como se fosse a revisão do inventário inteiro.

Campos locais sensíveis e paths não são publicados. Emitir nova sequência/atualizar TTL sem mudar digest quando a evidência não mudou; update de conteúdo com mesma versão muda digest.

### CON-R4-06 — Evento/ACK/recibo recuperáveis

Preservar namespace e connection origin nos ACKs; esperar target do batch; remote ACK e aplicação Core são fatos separados. Ler journal em páginas finitas. Backpressure não apaga receipt já produzido; reconnect retoma streams mesmo sem nova mensagem do harness. Queries históricas abrem journal sem binário.

### CON-R4-07 — Aprovação pelo dispatcher e chave completa

A CLI apenas propõe/consulta decisão. Após Server confirmar, operação de aplicação é recebida no WSS R4 e chama Core com request operacional original e argumentos nomeados. Não executar novamente em `approval.decision` notification ou depois do retorno HTTP. Preservar registro/tombstone por escopo e idempotência; retorno perdido não gera novo ID.

Input sensível segue o contrato de retenção explicitamente escolhido; sem prova de persistência recuperável, não anunciar recovery pós-crash de conteúdo bruto. Não ampliar autoridade do agente para substituir operador.

### CON-R4-08 — Lifecycle e pacote integrado

Conservar host/Core/store enquanto houver producer/recurso/obrigação; decisões de stop usam recibo e prova, não `stage != UNKNOWN`. Shutdown com unknown mantém supervisor/IPC de recuperação ou transferência de SO qualificada; exit code não é mecanismo de ownership. Pin exato de Core R4 e fixtures de dois namespaces; sem servidor ou proxy MCP.

## 4. O que o agente Server deve entregar aos outros dois

Entregar `/v1` protocol/me, registro executor, snapshots/realizações, prepare/apply, tickets, resolve/admit/query/receipts, capability, decisions e native-actions com OpenAPI/fixtures geradas dos schemas acordados. Entregar endpoint WSS R4 e peer de laboratório capaz de controlar abertura remota, ACKs, rotações, lease e falhas de resposta.

A fila de operação do Server é a única autoridade de execução; os mocks dos aplicativos devem representar essa regra. O peer não retorna sempre applied=true, READY ou lease estendida. Deve conseguir recusar, expirar, perder ACK depois de commit e consultar o mesmo resultado.

## 5. Ordem coordenada sem bloqueio circular

**Marco A — contrato:** Server NS00–NS03 e Core CORE-R4-01/02/03; Connector conclui CN5 e prepara DTOs. Os três agentes podem começar agora. A primeira entrega compartilhada é o contrato, não o provider inteiro.

**Marco B — inventário:** Core existente já permite catálogo/availability/ref. Server NS04/05 + Connector CON-R4-05 integram snapshot e seleção. UI pode usar fixtures do contrato enquanto endpoint é implementado, sem declarar integração completa.

**Marco C — uma execução:** Server NS06–NS09 e Connector CON-R4-02/03/04 atravessam open/submit/control/receipt com um peer de Core. Não aguardar a campanha multi-host para escrever remote open: isso geraria dependência circular.

**Marco D — governança:** ingressos/ACK/decisions/native-actions completam o ciclo. Então testar provider real local e remoto no mesmo wheel e ampliar casos.

**Marco E — release delimitada:** somente depois dos gates de plataforma/provider/aplicativos. Testes locais do Core não encerram o aceite do Server; XML de um repo não é nova execução em outro.

## 6. Lista de bloqueios legítimos

Bloqueia novo efeito remoto: bundle R4 não publicado, Connector sem remote open, lane sem ACK, sessão sem lease aplicada, snapshot stale, contexto incompatível ou pending decision sem autoridade. Não bloqueia desenvolvimento de UI, migrações, auth, catálogo ou domínio com fixtures.

Não aceitar como “bloqueio externo”: erro de namespace, código que ignora uma revisão, enum local duplicado, método não ligado ao caller, producer cancelado por waiter ou retorno falso de prontidão. Esses são defeitos da aplicação responsável e devem ser corrigidos nela.
