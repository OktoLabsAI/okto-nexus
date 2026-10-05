# Migração, operação, rollout e evidências

## 1. Política de mudanças

A implementação deve ser incremental e aditiva. Não reescrever a migração 029 nem assumir que a próxima disponível é 030. O Codex deve consultar as migrações do HEAD real e sua aplicação pelo MigrationRunner antes de escolher nomes/números.

O scope de compatibilidade é o comportamento legado sem a feature e as capacidades da PR habilitada após configuração explícita. Não preservar bugs como impersonação, auto-criação implícita insegura de Agent, default de divulgação de resultados ou mutação de perfis.

Nunca misturar versões de writers sem uma política de compatibilidade. Um processo antigo que não cria outbox/reservas pode violar a semântica da integração ativa. Registrar versão/capacidade do writer/store e usar a defesa já disponível no repo para bloquear writers incompatíveis enquanto as novas garantias estão habilitadas. Instalações legadas sem a integração mantêm seu funcionamento normal. Comparar a superfície OFF com o merge-base sem as novas tools da PR, não com o HEAD que já as publicava. Alterações inevitáveis de versão/schema ledger/relatório de flags são exceções de metadados explicitamente registradas; nomes, parâmetros e semântica das operações legadas não podem mudar silenciosamente.

## 2. Preparação e backup

Antes de migrar um store real, inventariar schema, quantidade de agentes/endpoints/sessões/entregas e operações não terminais. Registrar checksums/contagens de perfil para demonstrar que capabilities, tags, role, metadata, permissions e comm_scope não mudaram.

Fazer backup SQLite consistente com a ferramenta/API de backup apropriada ou procedimento offline controlado. Não copiar somente o `.db` de uma base WAL ativa ignorando arquivos necessários. Incluir artifact store e journal nos backups conforme seus watermarks/refs, documentando o ponto de consistência. Não salvar tokens em relatórios de migração.

O Codex deve testar restore em store temporário antes de declarar o procedimento pronto. Backup não é rollback automático de efeitos que os harnesses já produziram no filesystem, repositórios ou serviços externos.

## 3. Migração por cenários

### 3.1 Store anterior à integração

Aplicar migrations aditivas. Não criar endpoints executores para todos os agentes. Não emitir comandos, começar runtimes nem materializar outbox para todo histórico unread. Feature desligada significa zero novo dispatch, e o cadastro existente deve permanecer idêntico.

### 3.2 Store que já aplicou 029

Preservar `harness_sessions` e `harness_events` existentes, inclusive IDs, native_event, timestamps e sequência histórica. Adicionar colunas/índices de modo compatível com ausência de metadados antigos.

Criar bindings históricos somente quando a ligação ao agente e ao workspace puder ser provada. Dados ambíguos ficam `pending_review` e desabilitados, com motivo. Não usar o cwd atual do processo de migração como workspace de uma sessão antiga.

Sessões antigas `RUNNING`/`INTERRUPTING` são estado histórico, não liveness. Marcar a observação operacional como `unknown`/`requires_reconciliation`, sem inventar um horário real de término. Isso não exige reescrever toda a história para ENDED.

Perfis canônicos sobrescritos antes da migração só podem ser restaurados a partir de backup/evento/arquivo confiável com revisão de origem. Sem isso, emitir relatório de dano/ausência; nunca inferir skills de um nome de agente, harness ou papel aproximado.

### 3.3 Histórico de mensagens e sessões anteriores

Não reenviar mensagens unread antigas automaticamente para um runtime recém-ativado. O padrão é criar intents apenas para eventos novos após ativação. Um replay administrativo de backlog exige seleção de intervalo/IDs, preview de destinatários/bindings, política de dedupe e confirmação explícita do operador. Reusar IDs quando for retry da mesma intenção, não criar novo trabalho sem marcar essa intenção.

Eventos antigos sem operation_id devem continuar legíveis como `legacy_unlinked`; não inventar correlação retroativa. Um relatório pode sugerir possíveis vínculos para análise, mas essas sugestões não autorizam transições de trabalho.

### 3.4 Mudanças de schema e falhas

A migração deve ser transacional conforme a infraestrutura real permitir, manter FK/index constraints e falhar de forma recuperável em caso de interrupção. Testar reexecução do runner, restore e falha no meio da transformação. Não depender apenas de `IF NOT EXISTS` para afirmar que backfills e alterações de dados são idempotentes.

Novas tabelas de execução/histórico não podem ser apagadas por `ON DELETE CASCADE` de um Agent sem revisar o efeito sobre auditoria e dedupe. Preferir desativação/soft delete e tombstones quando isso for necessário para preservar operações pendentes e histórico. Verificar as cascatas já existentes em 029 e ajustar aditivamente se elas violarem a retenção necessária.

## 4. Flags e defaults propostos

Usar o mecanismo real de config do Nexus; não criar um segundo loader. Os nomes abaixo podem ser normalizados aos padrões existentes. Toda precedência CLI/env/store/default deve ser testada e exibida em diagnóstico redigido.

| Configuração lógica | Default proposto | Regra |
|---|---|---|
| `feature_harness_integrations` | false | Publicação das novas tools e admissão de novos comandos |
| `feature_harness_attach` | false | Opt-in adicional para protocolo attach não documentado |
| `harness_dispatch_enabled` | true quando a feature está ativa | Worker pertencente ao `serve`, nunca criado implicitamente pelo stdio |
| `harness_inherit_ambient_backend` | false | Requer perfil/opt-in explícito por endpoint |
| `harness_max_inflight_global` | 8 | Ponto de partida operacional, a validar no benchmark |
| `harness_max_inflight_per_lane` | 1 turno normal | Controles seguem a capacidade do adapter |
| `harness_reconcile_seconds` | 30 | Varredura interna de recuperação; não status polling do harness |
| `harness_max_relay_depth` | 4 | Não é reiniciado por TTL |
| `harness_max_generated_messages_per_root` | 32 | Reserva atômica, ramos incluídos |
| `harness_max_executions_per_root` | 16 | Quota independente de mensagens |
| `harness_root_deadline_seconds` | 1800 | Encerra root; não cria root substituto |
| `harness_journal_max_bytes` | obrigatório e finito | Escolher valor por capacidade local e expor uso/backpressure |
| `harness_backlog_limit` | obrigatório e finito | Aplicar antes de admitir trabalho que não pode ser retido |

Não tratar esses números como performance medida ou limite de produto definitivo. Timeouts de startup/write/aceitação/turn/stop devem ter nomes distintos, valores documentados e limites de batch/shutdown globais. Não reutilizar timeout de write como prazo máximo de inferência.

Desligar a feature em runtime bloqueia novas admissões e publicação futura da superfície após restart; não apaga intents nem cancela a captura dos resultados em trânsito. Workers necessários a drenar/reconciliar continuam no modo de manutenção até produzir estado seguro. Um hard stop precisa registrar estados desconhecidos, sem liberar novos consumidores automaticamente.

## 5. Rollout em etapas

### Etapa A — Flag desligada

Aplicar schema e rodar a regressão legada. Verificar agentes intactos, inbox original, ausência de supervisor nos processos stdio e ausência de ferramentas de runtime para clientes não habilitados.

### Etapa B — Planejamento sem envio

Em store de teste, executar o planner com adapters `dry_run`. Não criar duas intents reais de execução em paralelo. O modo dry-run precisa ser marcado como tal e nunca reconhecer uma mensagem como aceita pelo harness.

Comparar seleção, políticas, reservas e envelope esperado para direct/capability/role/tag/broadcast. Não espelhar prompts para um backend real apenas para comparar caminhos.

### Etapa C — Um binding por vez

Habilitar cada conector com backend explicitamente autorizado, seguindo a matriz de capacidades. Executar conversa multi-turn, controle suportado, geração de resultado e recuperação. Attach usa sessão interativa dedicada para teste; não injetar em sessões pessoais encontradas no registry.

### Etapa D — Multiendpoint/multiagente

Habilitar duas conexões da mesma identidade, dois workspaces e participantes distintos. Executar concorrência de inbox/push, handoff competitivo, relay A→B→C, interrupção e respostas tardias. Confirmar que réplicas de observação não recebem comandos executores.

### Etapa E — Falhas e carga

Aplicar fault injection e stress sobre scheduler, storage, IPC e processo. Testar recuperação de intenção/resultado com crash real além de mocks. Medir bounds, leak e backlog em ciclos repetidos.

### Etapa F — Liberação

Atualizar documentação, índice de evidência, capability matrix e release notes. Definir versões de binário comprovadas e bloquear apenas capacidades incompatíveis, com diagnóstico. Não afirmar que uma versão de protocolo é estável ou suportada apenas porque constava do texto original da PR.

## 6. Rollback operacional seguro

Rollback primário é desabilitar novas admissões e drenar/reconciliar, não remover tabelas nem ligar o callback antigo.

1. Bloquear novos comandos/claims executores da integração e manter reads/diagnóstico autorizados.
2. Parar novos claims de dispatch; registrar intents pending, sending e accepted.
3. Drenar journal e projetar resultados já capturados; preservar resultados tardios e ownership.
4. Encerrar apenas processos gerenciados autorizados. Desanexar attach, sem matar o processo externo.
5. Reconciliar `SENDING`/`UNKNOWN`. Não liberar fallback executor porque o recurso foi desligado.
6. Liberar a inbox para fallback somente para operações provadamente não enviadas ou em takeover explícito com risco reconhecido.
7. Manter schema e registros de dedupe. Só usar binário anterior se sua compatibilidade de schema/semântica tiver sido demonstrada; caso contrário, permanecer em modo desabilitado da versão corrigida ou restaurar backup offline após análise dos efeitos externos.

Não iniciar o novo dispatcher e o `_on_inbox_delivery` antigo para o mesmo destinatário. O cutover deve ser único, com ownership/verificação em teste. Também não admitir replay a partir de um restore enquanto um owner/processo antigo ainda está produzindo efeitos.

## 7. Operação e diagnóstico

Disponibilizar pelo dashboard/API administrativa os casos `NO_LIVE_ENDPOINT`, `AMBIGUOUS_BINDING`, `WAITING_APPROVAL`, `OUTCOME_UNKNOWN`, `SENT_UNCONFIRMED`, `JOURNAL_BLOCKED`, `PROTOCOL_UNSUPPORTED`, `CLAIM_STALE` e `RELAY_BUDGET_EXCEEDED`, normalizados ao catálogo de erros real.

Para cada operação mostrar request/operation/delivery/handoff IDs, ator e agente representado, workspace, endpoint/session, tentativa/epoch, timestamps, última evidência de aceitação, estado do resultado e motivo de bloqueio. Não expor tokens, payloads fora da audiência ou configuração privada.

Ações administrativas de retry/reconcile/takeover devem exigir autorização específica, idempotency key, reason e validação de elegibilidade. “Retry” indiscriminado não pode reexecutar operações aceitas ou desconhecidas. Uma decisão manual de repetir apesar da incerteza cria um registro explícito de risco e relação com a operação anterior.

### Métricas mínimas

Medir enqueue latency, commit→dispatch, time-to-first-event, accepted→terminal, terminal→durable/projected, intents por estado, fila por lane, retry seguro, unknown/unconfirmed, suppressions de duplicate, budgets, autorizações negadas, journal bytes/lag, eventos sem correlação, active runtimes, processos órfãos, threads/FDs e tempo de shutdown.

Métricas devem usar labels de cardinalidade limitada. IDs individuais e conteúdo pertencem a logs/eventos autorizados, não a labels de métricas. Telemetria externa não deve receber prompts, secrets, paths ou perfis privados por efeito dessa mudança.

Backlog cheio pode negar a admissão de um comando executor com erro de capacidade antes de efeitos. Para uma mensagem já persistida cuja intenção aguarda transporte, mostrar `waiting/backpressure` sem declarar perda. Separar limites da entrega informativa e da execução de trabalho para não corromper a semântica da inbox.

## 8. Contrato de evidência

Cada caso executado deve registrar:

```text
test_id / requirement_ids
repository, head_sha, base_sha, dirty_tree_diff_hash quando houver
os, architecture, Python/dependencies pertinentes
adapter_id, binary_path redigido, binary_version, protocol/schema hash
backend_profile_id (sem credentials)
command/fixture/seed/fault injection point
observed_before / observed_after
trace interval e IDs que vinculam request→intent→attempt→native event→result
expected outcome / actual outcome
status: PASS | FAIL | NOT_RUN | NOT_APPLICABLE
limitation / reason / evidencia referenciada
```

`NOT_APPLICABLE` exige incompatibilidade estrutural comprovada, como steering no attach que não o oferece; ausência de binário, credencial, tempo ou ambiente é `NOT_RUN`. A matriz declarada do adapter e o teste precisam concordar.

Um teste com fake verifica a lógica do Nexus, não prova o protocolo nativo. Um teste real verifica o protocolo naquela versão/configuração, não todos os ambientes. Combinar ambos e rotular explicitamente.

O evidence index final deve ser gerado das entradas de resultado, evitando totais escritos à mão. Contagens antigas ficam sob uma seção histórica com SHA/data e não são somadas ao resultado atual.

## 9. Performance e prova de não regressão

Os primeiros gates são mecanísticos: enqueue conclui sem desbloquear o conector travado; nenhuma chamada de rede é observada dentro de UoW; filas/threads permanecem sob o cap; uma lane lenta não impede o controle da outra; nenhuma consulta de status do harness aparece no intervalo do turno.

Os benchmarks usam a mesma máquina, dataset e versões antes/depois, aquecimento documentado, várias repetições e percentis. Registrar o overhead de fsync e de policy; não remover durabilidade para melhorar o gráfico.

Distinguir tráfego de polling de comandos legítimos como approve/steer/interrupt e de IPC de wake. A frase aprovada é: “entrega e resposta nativas orientadas a eventos, sem polling do harness no caminho nominal; recuperação interna durável com reconciliação limitada”. Não prometer ausência absoluta de timers, polling de recuperação ou leitura de banco.

Nenhuma otimização deve manter um resultado apenas em memória para cumprir latência. Quando a garantia de durabilidade precisa de um custo mensurável, publicá-lo e manter o estado transitório/durável explícito.

## 10. Entregáveis no repositório

Manter código e migrações nos locais convencionais. Em `plans/pr34-remediation/`, manter baseline, mapa de contratos, defect register, status, backlog e decisões arquiteturais. Em `docs/harness-integrations/`, atualizar operator guide e evidence index; adicionar guia de migração/recuperação.

Relatório de entrega deve conter: resumo das mudanças, mapa F01–F14→código/testes, migrações e compatibilidade, resultados unit/integration/native, métricas, limites ainda inerentes aos protocolos e prontidão de merge. Nunca concluir “todos resolvidos” quando o caminho nativo que sustenta uma capacidade ainda está `NOT_RUN`.
