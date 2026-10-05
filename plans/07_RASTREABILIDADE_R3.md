# Rastreabilidade e substituição do plano Server R3

R4 substitui o backlog ativo do Server, não apaga requisitos. Cada linha original abaixo tem sucessores explícitos; os 45 TN e 34 J foram incorporados à matriz com estado NOT_RUN. Os planos do Core/Connector não são considerados implementados porque seus requisitos foram mapeados.

| Tarefa R3 | Requisito original | Tarefas R4 |
|---|---|---|
| N00.1 | Registrar HEAD/branch/working tree, versões Python/MCP/schema, comandos de build e testes; preservar arquivos modificados e falhas preexistentes separadas. | NS00.01, NS16.02 |
| N00.2 | Ler os dois planos anteriores, PR34 e remote-executors; criar crosswalk G01–G20 e marcar cada requisito como preservado, substituído, já implementado ou a investigar. | NS00.02 |
| N00.3 | Inspecionar fluxo de chave, cache, middleware, operador reservado, grants e self-open; demonstrar que chave resolve agente e que emitir nova chave invalida a anterior. | NS03.01, NS03.05 |
| N00.4 | Reproduzir setup local e bugs de argv/path/plataforma no HEAD; criar regressões para os confirmados, sem tratar comentários/planos como evidência de execução. | NS00.05, NS07.02 |
| N00.5 | Inventariar realpath, spawn, ownership, delivery, approvals, boot e todo MCP stdio (entrypoints/config/módulos/docs/testes); medir baseline MCP HTTP e instalar backlog/status/evidência da revisão 3. | NS01.01, NS01.02 |
| N01.1 | Consumir bundle imutável K01 com manifest/hash; integrar tipos via API pública sem manter cópia autoral de NXL no Server. | NS00.03, NS00.04 |
| N01.2 | Modelar executor/binding/workspace binding, credential epoch, auth/config revision, operações e eventos; preservar IDs e serviços existentes onde possível. | NS02.01, NS02.02 |
| N01.3 | Criar migrações aditivas idempotentes e índices por key hash, agente/binding/executor/workspace e operation/event IDs; definir backfill retomável. | NS02.02, NS15.01 |
| N01.4 | Definir porta de execução embutida/remota, contexto autenticado e rotas do Anexo A no OpenAPI do produto; fechar validação de entrada/erro antes de efeitos. | NS06.01, NS08.01 |
| N01.5 | Construir reader/writer fixtures legado-novo, testes de boundary e de conflito; registrar política de rollback e incompatibilidade de schema sem downgrade destrutivo. | NS15.01, NS15.04 |
| N02.1 | Implementar /connections/me utilizando o resolvedor de chave existente; comparar agent hint e negar spoofing sem enumerar agentes. | NS03.01 |
| N02.2 | Implementar prepare/apply de binding próprio com CAS, políticas existentes e aprovação agregada; agente não pode habilitar método negado ou se autoaprovar escalada. | NS03.02, NS05.03 |
| N02.3 | Emitir tickets opacos curtos escopados em agente/executor/binding/epoch e capacidades de sessão; não adicionar login de usuário nem chave raiz obrigatória de Connector. | NS03.03, NS03.04 |
| N02.4 | Propagar rotação/revogação para tickets NXL, capabilities MCP HTTP diretas, caches, lanes, leases e bridges não MCP; validar cada audiência sem permitir bypass quando apenas um canal estiver conectado. | NS14.02, NS09.04 |
| N02.5 | Gerar contrato de comando de conexão da tela do agente; importar chave existente por entrada protegida e nunca emitir outra para contornar hash-only; testar comando em shells suportados. | NS03.05 |
| N03.1 | Integrar wheel incremental do Core ao serve e serve-lite; montagem de API/dashboard sem provider/binário local continua válida. | NS01.03, NS07.01 |
| N03.2 | Criar EmbeddedExecutor adaptando journal/event sink/secret resolver e contexto autorizado; não usar WSS/Connector app para executar localmente. | NS07.01, NS07.02 |
| N03.3 | Substituir construção nativa em RuntimeOpen/Control pelo despacho da porta; preservar recibos, reserva idempotente e claims existentes. | NS06.02, NS07.02 |
| N03.4 | Separar supervisor canônico de processo físico; manter wrappers de compatibilidade temporários e eliminar duplicação de adapters após comparação rastreada. | NS15.03 |
| N03.5 | Integrar startup/shutdown do Core ao owner de serve, contenção, readiness e cleanup; CLI/cliente MCP HTTP não são donos de runtime e nenhum processo MCP stdio inicia o Server. | NS07.05, NS14.03 |
| N04.1 | Usar discovery/prepare do Core no executor certo; Server central consulta inventário remoto e nunca qualifica peer pelo próprio os.name. | NS04.01, NS04.02 |
| N04.2 | Implementar criação/resolução de workspace lógico e vínculo físico local com validação no executor; manter aliases de IDs legados e compatibilidade de APIs. | NS02.04, NS05.01 |
| N04.3 | Criar fluxo resolve–diff de confiança–approve/apply–start com etapas reexecutáveis; gerar endpoint/perfil/argv sem pedir ao usuário sua estrutura interna. | NS05.02, NS05.03 |
| N04.4 | Reutilizar binding e sessão compatível, com ambiguidade explícita e intenção nova para --new-session; mudança de root/perfil/harness não amplia escopo silenciosamente. | NS05.04 |
| N04.5 | Corrigir fluxo do campo Executável para consumir templates de Core; segredos/provider home são refs locais e login ausente retorna ação no host adequado. | NS05.05, NS07.03 |
| N05.1 | Implementar upgrade WSS com TLS no deployment, ticket em header, subprotocolo nxl.v1, negociação de limites e erro antes de efeitos para versão incompatível. | NS08.01 |
| N05.2 | Registrar connector/executor como entidades técnicas; autenticar lane inicial e binding.attach adicional com prova de agente independente por ticket. | NS03.03, NS08.02 |
| N05.3 | Gerir geração/ownership de canal por CAS, reconnect, heartbeat, lease autenticado e conflito entre instâncias; não converter WSS ativo em runtime pronto. | NS08.03, NS09.02 |
| N05.4 | Implementar inventory snapshot/delta, filtros por binding e estado de controle; não aceitar atualização global de identidade/permissões vinda do executor. | NS04.03, NS04.04 |
| N05.5 | Adicionar prioridades, limites de bytes/frames, redaction e backpressure; validar proxy reverso e fechamento/deauth por agente sem conceder outra lane. | NS08.04, NS08.05 |
| N06.1 | Reservar operação/outbox com ID/hash antes do envio; mesma intenção retorna recibo, payload conflitante é negado; rede/spawn nunca dentro da transação. | NS06.01, NS06.02, NS06.04 |
| N06.2 | Ingressar eventos com identidade/sequence/hash e ACK pós-commit; projetar fatos idempotentemente e lidar com terminal antes de ACK intermediário. | NS10.01, NS10.03 |
| N06.3 | Reconciliar cursores, operações, sessões e ownership após reconnect/restart; conservar unknown e evitar repetição automática ou realocação para outro executor. | NS14.01, NS09.04 |
| N06.4 | Aplicar mecanismo de consumo exclusivo comum a MCP/local/remoto; preservar quotas, leases, causalidade e budgets ao reconectar. | NS06.05, NS12.01 |
| N06.5 | Testar queda em cada fronteira de commit/envio/aceitação/evento/ACK, evento atrasado e geração antiga; diferenciar evidência histórica de autoridade ativa. | NS10.05, NS16.02 |
| N07.1 | MCP HTTP do Server e bridges nativas não MCP chamam os mesmos casos de uso; Core não importa MessageService nem concede grants. Não criar fachada MCP local/remota. | NS12.01, NS12.02 |
| N07.2 | Emitir capability de sessão aceita diretamente pelo MCP HTTP com agente/workspace/binding/sessão/ações/validade; qualificar renovação e expiração sem proxy/hot-reload presumido, nem chave administrativa no harness. | NS03.04, NS09.05 |
| N07.3 | Distinguir fim de turno de handoff complete; preservar claim, reply target, contexto, evidência, root/parent/correlation e orçamento de relay. | NS12.03 |
| N07.4 | Normalizar pedidos HITL com sessão/turno/request/geração/expiry; aplicar decisão uma vez por CAS e validar autoridade existente de aprovador. | NS11.01, NS11.02, NS11.03, NS11.04, NS11.05 |
| N07.5 | Classificar execute_work somente após caminho de ferramentas comprovado; MCP HTTP direto é padrão para cliente compatível. Pi sem esse cliente usa extensão nativa não MCP qualificada, nunca servidor/proxy MCP. | NS07.04, NS12.04 |
| N08.1 | Expor operações por intenção nas superfícies existentes, compartilhando validação/autorização; evitar tool por host/adapter/CRUD interno. | NS12.05, NS06.01 |
| N08.2 | Implementar namespace CLI runtime com discover/start/status/interrupt/stop/logs/doctor e recibos JSON; não sobrecarregar start como daemon e harness. | NS13.04 |
| N08.3 | Remover MCP stdio, entrypoints e shims legados do Nexus; migrar configuração selecionada para MCP HTTP direto sem rotação de key/novo agente. Preservar outras entradas e SDK major; roots/hints não autorizam filesystem/identidade. | NS01.02, NS01.05 |
| N08.4 | Gerar configuração do cliente MCP HTTP para a URL do Server e capability limitada de sessão, inclusive local nativo. Não exigir Connector ou publicar fachada/backend MCP adicional; validar alcance a partir do harness/sandbox. | NS07.03, NS12.02 |
| N08.5 | Medir catálogo/tokens antes/depois e corrigir crescimento desnecessário; erros de auth/projeto/unknown são prescritivos sem rotinas manuais de grants. | NS12.05 |
| N09.1 | Criar visão por agente com local/remoto/tools-only/managed/attach e host/projeto/status; não adicionar painel de conta de usuário Nexus. | NS13.01, NS13.02 |
| N09.2 | Implementar gerar comando protegido para Connector e fluxo local nativo; renderizar política/aprovação agregada em linguagem de intenção. | NS03.05, NS13.02 |
| N09.3 | Retirar JSON, nomes/IDs de endpoint/perfil, argumentos e token de uma hora do caminho normal; avançado apenas para diagnóstico e opções justificadas. | NS13.02 |
| N09.4 | Implementar start/reuse/interrupt/stop/inspeção/logs com recibos e estado de operação; timeout não dispara nova sessão automaticamente. | NS13.03, NS13.04 |
| N09.5 | Mostrar desconhecido/offline/auth_required/drift/approval por camada e capabilities reais; testar UI em locale/shell/path com espaços e preservação de config MCP. | NS13.05 |
| N10.1 | Executar testes de spoof de agente/Server/executor, replay de ticket, lane não autenticada, mutation de escopo e tentativa de plugin/shell remoto. | NS08.04, NS09.04 |
| N10.2 | Validar invalidation de chave em trânsito e revogação durante turno/approval; impedir renovação após revogação e mostrar limite real de partição/lease. | NS14.02, NS09.05 |
| N10.3 | Exercitar frame/journal flood, slow consumer, disco cheio e controle urgente; recursos finitos e isolamento por binding/Server são obrigatórios. | NS08.05, NS14.04 |
| N10.4 | Validar restart do owner, morte do executor local e reconnect remoto com operações desconhecidas; não converter heartbeat em prova de processo vivo/morto. | NS14.01, NS14.03, NS14.05 |
| N10.5 | Auditar logs/metrics/export/UI para secrets e roots indevidos; separar dados históricos de geração antiga de nova autoridade e registrar findings resolvidos. | NS13.05, NS16.02 |
| N11.1 | Executar cenário sintético de 100 mil agentes sem providers: onboarding por key index, paginação, sem full enumeration ou estruturas por identidade offline. | NS03.01, NS14.04 |
| N11.2 | Limitar cache positivo por tamanho/TTL com invalidação síncrona; medir touch/queries no hot path e evitar escrita por delta de streaming. | NS14.04 |
| N11.3 | Migrar instalação legada, permissões e endpoints para executor local; comparar dados/IDs/inbox/handoff antes/depois e retomar backfill interrompido. | NS15.01, NS15.02 |
| N11.4 | Remover código nativo duplicado após paridade, referências ao Core hospedado no Connector e onboarding user-centric; marcar planos antigos superseded preservando evidência. | NS15.03, NS00.02 |
| N11.5 | Entregar runbooks de backup/restore/rollback e upgrade com drain; não indicar downgrade de schema irreversível como seguro. | NS15.04, NS15.05 |
| N12.1 | Gerar wheel/sdist de Nexus com dependência Core versionada e assets corretos; instalação limpa sem clone do Connector. | NS16.01 |
| N12.2 | Rodar suíte unitária/contrato/migração e gate local com Core real; registrar versões dos harnesses e capacidades testadas por SO. | NS16.02, NS16.03 |
| N12.3 | Validar Server central sem binários/providers/dirs, preparando artefato para campanha remota; falhas locais do provider não impedem serving de modo remoto. | NS04.01, NS16.04 |
| N12.4 | Publicar documentação de API/CLI/UX e matriz de compatibilidade, sem comandos fictícios marcados como já existentes antes da implementação. | NS15.05, NS13.04 |
| N12.5 | Entregar build imutável de integração, SHA e hash para C11/N13; preparar release/rollback sem publicar automaticamente. | NS16.01, NS16.05 |
| N13.1 | Montar Nexus A sem runtimes e hosts B/C com Connector/Core, ao menos uma combinação heterogênea; incluir cenário Nexus local separado. | NS16.04 |
| N13.2 | Executar J01–J34 com SHAs e wheels reais; fakes não contam nos casos explicitamente multi-host/provider/SO. | NS16.04 |
| N13.3 | Validar first-use/second-use, chave MCP reutilizada, mesma identidade, múltiplos bindings e ausência de usuário Nexus em todas as superfícies. | NS13.02, NS16.04 |
| N13.4 | Injetar partições/restart/revogação/ACK perdido e provar não duplicação, cleanup e governança; registrar limitações por capacidade real. | NS14.05, NS16.04 |
| N13.5 | Consolidar matriz conjunta idêntica à do Connector/Core, blockers e release checklist; concluir somente gates demonstrados sem merge/publicação implícitos. | NS16.05 |

## Alterações normativas em relação ao texto R3

1. API pública real do Core substitui as assinaturas apenas ilustrativas de R3; instalação e availability v2 estão identificadas.
2. Novo /v1 direto é distinto do /api/v1 legado.
3. Server é o único admitter/dispatcher de efeitos; resolve não executa e receipt tem rota própria.
4. Catálogo/availability/snapshot são do executor escolhido; binding leva ref+revisão, não enum/local path central.
5. NXL R4 coordenado adiciona confirmações/correlação e payloads fechados; r3 histórico permanece imutável.
6. Decisão canônica gera a operação de aplicação; CLI não aplica nativo em paralelo.
7. DRAINING_PENDING conserva supervisor até prova ou transferência qualificada.
8. Core .10 e Connector .4 são baselines, não declaração de G2/E2.

## Correções acumuladas que viraram critérios permanentes

CN1/CN2: namespace completo, autenticação de todos os frames, idempotência HTTP, controle sob carga, scopes nos ACKs e história sem binário. CN3: gerações/revisões, quota exata, duplicate ACK e config por ownership. CN4: decisão Server antes de Core, candidato inteiro, revisão completa e rotação de lane. CN5: hash operacional não redigido, SessionKey até a aprovação, produtor separado do waiter, reattach após cancelamento e publicador retomado sem evento novo. Cada grupo aparece em NS08–NS14 e na matriz TR4. Não foram executados novamente nesta elaboração.