# Recuperação e disponibilidade dos runtimes

Estado: implementação iniciada. Data: 2026-10-16.

## Objetivo e limites

Eliminar bloqueios prolongados de agentes por falhas recuperáveis de startup,
reconexão e publicação de histórico. Uma falha de sessão deve ocupar somente os
recursos que ainda possam estar sob seu controle. O usuário deve intervir apenas
quando não houver prova técnica suficiente para uma recuperação segura.

Este plano cobre Nexus, Connector Core e Connector, mantendo Pi, Claude e Codex,
sessões persistentes e one-shot, pools, ferramentas injetadas e MCP. Não inclui
restaurar attach, trocar protocolos de harness, adotar Kubernetes/Temporal,
adicionar um broker externo ou executar processos em contêineres. Um supervisor
separado será primeiro um experimento com critérios de decisão explícitos.

Versões de desenvolvimento existentes, sem novo bump nesta etapa:

| Repositório | Versão/branch | Core consumido |
|---|---|---|
| Nexus | `0.3.1` / `feature/v0.3.1` | `0.0.12` |
| Connector Core | `0.0.12` / `feature/v0.0.12` | — |
| Connector | `0.0.10` / `feature/v0.0.10` | `0.0.12` |

Cada milestone concluído recebe validação, atualização do ledger, commit e push
nos repositórios afetados. Não há publicação PyPI, tag ou merge neste plano.
Se uma dessas versões for publicada por outra frente antes da conclusão, parar
a reutilização da versão e definir o próximo bump antes de gerar artefatos.

## Evidências e diagnóstico inicial

1. `CoreRuntime.open` registra `ProcessBirthEvidence` somente após o retorno de
   `native_factory.open`. O bridge pode aguardar startup/handshake antes disso.
   Uma operação pode ficar incerta sem identidade durável do processo criado.
2. Cancelar a espera não encerra uma thread de startup. A liberação de capacidade
   exige conter o processo e impedir que o produtor antigo ainda o crie.
3. A recuperação local percorre registros históricos e pode ligar a prontidão
   do agente à conclusão de pendências de publicação/receipts.
4. Local e remoto têm caminhos de recuperação diferentes. As regras de
   contenção, receipts, gerações e ACKs devem ser compartilhadas.
5. Já há portas de pool, fila, outbox, journal e ArtifactStore. Preservá-las e
   simplificar suas responsabilidades é preferível a introduzir infraestrutura.
6. O incidente Pi incluiu closes sem receipt após desconexão. A correção já
   existente exige prova de sessão/lease encerrada; não inventa sucesso nem
   repete a operação. Isso não resolve a janela de startup sem birth record.

Referências de implementação: Core `runtime.py`, `journal.py`,
`native/runtime_bridge.py`, `native/process/`; Nexus `bootstrap/embedded_*`,
`application/execution_*`, `application/resource_pool*`; Connector
`services/core_host.py`, `services/r4_reconciliation.py`, `transport/r4_*`.

## Invariantes obrigatórias

- Efeito possível nunca é reenviado automaticamente como se não tivesse ocorrido.
- PID isolado não prova identidade. Usar birth token e container/guardian próprio.
- Slot incerto continua contabilizado até prova de término e exclusão do produtor.
- Geração antiga não cria processo nem executa comando após perder autoridade.
- Cancelamento da espera não significa cancelamento do trabalho subjacente.
- Reinício, mudança de versão ou atraso do histórico não revogam uma configuração
  válida. Falha técnica observada pode impedir somente a operação afetada.
- Leases, revogação e permissões valem igualmente para MCP e ferramentas injetadas.
- Aquecimento e chamadas independentes progridem em paralelo, com limites de
  recursos. Não haver lock global mantido durante I/O de harness ou recuperação.
- Sucesso/falha final é durável e chega ao chamador; incerteza permanece explícita.
- Controle, contenção e respostas finais não ficam atrás de grandes eventos.
- Sessões persistentes não recebem comandos concorrentes sem suporte do harness.
- Reinstalação/restart do Nexus não é tratamento de uma falha sem diagnóstico.

## Arquitetura proposta

O domínio distingue cinco observações: conexão com o host, autoridade/lease,
recursos físicos e lógicos, resultado da operação e sincronização do histórico.
Um status agregado de UI é derivado dessas observações; não é fonte de verdade.

O host é dono dos processos e da contenção. O Core aplica regras de execução,
identidade, gerações e receipts. Nexus decide admissão, fila, configuração e
projeções. O Connector transporta os mesmos contratos para outro host. Adaptadores
de infraestrutura implementam armazenamento, processos e transporte, sem inserir
essas dependências no domínio do pool/fila.

Fluxo de startup final pretendido:

1. Admitir a chamada e reservar capacidade transacionalmente.
2. Persistir intenção, identidade do container e geração do produtor.
3. Criar o processo sob contenção e persistir sua identidade antes do handshake.
4. Confirmar protocolo/prontidão; só então oferecer a instância ao pool.
5. Em falha, cercar o produtor, conter o container e registrar a prova de término.
6. Liberar o slot comprovadamente encerrado e repor o pool de forma independente.

Uma intenção durável não prova que o processo existe; a ausência do birth record
não prova que não existe. O marco M2 trata explicitamente essa distinção.

## Milestones e critérios de aceite

### M0 — Baseline rastreável (três repositórios)

- Preservar as correções locais anteriores de artefatos, settings, resultado
  parcial, contenção SQLite e closes liberados, sem misturá-las com o protocolo novo.
- Conferir versões, dependências, vendor wheels e diferenças; registrar evidências
  existentes e executar regressões diretamente relacionadas.
- Registrar este plano e ledgers; criar/publicar as branches existentes no origin.
- Aceite: três commits de baseline publicados, pins coerentes e ausência de
  credenciais introduzidas nos arquivos adicionados.

### M1 — Identidade do processo antes do handshake (Core; integração dos consumidores)

- Adicionar uma notificação de nascimento no ponto comum de criação dos processos
  gerenciados. Pi, Codex e Claude devem usá-la sem aguardar resposta do harness.
- Core associa a notificação ao opening claim original e persiste pelo journal.
- Uma falha de persistência impede continuar o startup e provoca contenção; não
  permite publicar uma abertura bem-sucedida. A incerteza continua conservadora.
- Preservar compatibilidade com factories sem o novo parâmetro e a gravação
  idempotente após abertura para adaptadores legados.
- Testes: handshake bloqueado; gravação falha; isolamento entre dois startups;
  cancelamento do chamador; registro imutável/reabertura; adapters existentes.
- Aceite: birth record consultável enquanto o handshake ainda está pendente,
  nenhuma abertura confirmada sem gravação exigida, nenhuma sessão cruzada.
- Limitação explícita: ainda existe a janela entre criação nativa e gravação.

### M2 — Intenção durável, contenção identificável e produtor cercado

- Contrato versionado de launch intent: operação, sessão, executor, geração,
  identidade do container, estado/prova e revisão. Sem argumentos ou segredos.
- Persistir identidade antes do spawn. Transições CAS monotônicas e idempotentes.
- Windows: Job Object com identidade persistida e vínculo atômico ao processo;
  Linux/macOS: guardian/serviço equivalente qualificado por plataforma.
- Fechar a autoridade do produtor antigo antes de inferir ausência/encerramento;
  observar/encerrar container, sem adotar ou matar processos por PID reutilizado.
- Recuperar intenções interrompidas sem replay de comandos. Registros antigos sem
  prova suficiente mantêm comportamento conservador e diagnóstico explícito.
- Testes de crash em cada fronteira: antes/depois de intenção, container, spawn,
  birth, handshake, receipt e ACK; thread atrasada após cancelamento/revogação.
- Aceite: startup interrompido converge automaticamente quando há prova; nenhuma
  liberação antecipada, spawn tardio autorizado indevidamente ou efeito duplicado.

### M3 — Disponibilidade por recurso e recuperação isolada (três repos + UI)

- Modelar separadamente conexão, autoridade, capacidade e sincronização.
- Pending de histórico não bloqueia capacidade independente; slot físico incerto
  permanece ocupado. Não redirecionar uma conversa persistente ainda incerta.
- Reconciliador por entidade com orçamento, backoff+jitter e uma tentativa ativa;
  erro de um agente não cancela tasks dos demais.
- Preservar primeira causa, atualizar causa atual, progresso, próxima tentativa e
  ação excepcional permitida; expor em Agents/Graph/consultas com mesma semântica.
- Testes: um harness trava, outros executam; filas mantêm deadline e erro ao
  chamador; reconexão/versionamento não exige revisão manual sem falha técnica.
- Aceite: nenhuma dependência de histórico para admitir trabalho independente e
  nenhuma violação de capacidade ou autorização nos casos de incerteza.

### M4 — Recuperação incremental e justiça entre streams

- Índice durável de pendências e checkpoints terminais; atualizar com a mesma
  transação do journal/outbox, sem segundo estado divergente.
- Recuperar pendências/ativos por lotes e cursores. Backfill compatível e resumível
  para journals antigos; auditoria completa fora do caminho de admissão.
- Separar orçamento de controle/resultado do volume de artefatos; retry apenas na
  fronteira idempotente, sem repetir escrita nativa por erro SQLite/transporte.
- Testes: reinício entre transações/checkpoints, eventos grandes, disco cheio,
  SQLite ocupado, histórico de 1k/10k/100k sessões com mesmo conjunto de pendências.
- Aceite: trabalho de reconciliação é proporcional às pendências após backfill;
  nenhum ACK avança além de dados duráveis, nenhum stream causa starvation.

### M5 — Núcleo compartilhado de recuperação local/remota

- Extrair políticas de estado/transição para Core e manter adaptadores de host no
  Nexus/Connector. Remover duplicação somente após testes diferenciais.
- Unificar interpretação de close sem receipt, prova de contenção, retomada de
  stream, geração/lease e versões de contrato; negociar extensão quando necessário.
- Rodar o mesmo roteiro pelo embedded e pelo Connector local em processo separado.
- Aceite: resultados equivalentes para mesmas evidências, inclusive retransmissão,
  perda de receipt, revogação, reconnect e reset com preservação de agentes.
- Host remoto físico será uma qualificação posterior com o usuário; teste em
  loopback não será descrito como validação em outra máquina.

### M6 — Experimento de supervisor independente por host

- Primeiro ADR e protótipo isolado: processo por usuário/host, IPC autenticado
  (named pipe no Windows/socket local onde suportado), uma autoridade de processo.
- Nexus pode reiniciar enquanto supervisor mantém contenção, spool e leases
  limitadas. Desconexão não concede autorização indefinida para novas ações.
- Comparar com embedded atual: disponibilidade durante restart, custo de memória,
  instalação/update, shutdown, credenciais, suporte Windows e recuperação do host.
- Aceite para adoção: redução demonstrada de indisponibilidade sem perda de
  revogação/isolamento; serviço deve poder atualizar e recuperar sem duplicar donos.
- Decisão registrada antes de migrar o padrão. Se não melhorar o resultado, manter
  o host compartilhado em biblioteca; não carregar dois ciclos de vida permanentes.

### M7 — Pool e startup com orçamento e prioridade

- Requests pendentes aproveitam primeira instância pronta; warmup independente,
  concorrente e limitado por orçamento físico do host, além do limite por agente.
- Separar contagem disponível, em startup, ocupada, drenando e incerta; não chamar
  uma reserva de instância pronta. Reposição somente após liberação comprovada.
- Alteração de configuração drena geração antiga e repõe nova com decisão explícita
  sobre sessões ativas; fila tem limite/deadline e rejeição observável ao chamador.
- Medir p50/p95/p99 de admissão, cold start, warm dispatch e tempo em fila por
  harness; identificar verificações caras e cachear apenas sob identidade válida.
- Aceite: chamadas paralelas não viram startup sequencial por lock/validação global;
  limite finito respeitado e modo ilimitado ainda sujeito a recursos reais do host.

### M8 — Qualificação, instalação e fechamento

- Matriz integrada abaixo, wheels instaladas em ambiente limpo, pins e vendors
  regenerados a partir dos commits de implementação. Nenhum teste apenas de source
  será usado como evidência de que a instalação foi atualizada.
- Comparar baseline e novo comportamento sob mesma carga, documentando hardware,
  versões de harness, configuração, tempos e limites dos testes.
- Preparar atualização reversível do ambiente local; manter backup compatível de
  banco/journals antes de migração. Upgrade/downgrade deve detectar incompatibilidade,
  nunca apagar evidência ou reinterpretar processo incerto como livre.
- Aceite: zero chamadas admitidas sem resultado/erro rastreável, zero processos
  órfãos no cenário qualificado e recuperação automática com ambiente estável.
- PRs/main/tags/publicação serão uma etapa separada se solicitada.

## Matriz mínima de validação

| Eixo | Casos obrigatórios |
|---|---|
| Harness | Pi, Codex, Claude; fake determinístico e processo nativo na qualificação |
| Transporte | Embedded, Connector local separado; remoto físico pendente de host |
| Sessão | Persistente, one-shot; warm/cold; múltiplas chamadas e handoff broadcast |
| Falha | Crash Nexus, crash host, startup travado, processo morto, rede interrompida |
| Fronteira | Reserva/intenção/spawn/birth/handshake/receipt/evento/ACK/checkpoint |
| Pressão | Fila cheia, deadline, CPU, SQLite busy, grandes eventos, disco/quota cheia |
| Segurança | Revogação, lease expirada, geração antiga, PID reutilizado, MCP/injeção |
| Configuração | Novo agente durante recovery, versão de harness, edição/drain/reset |
| Observabilidade | Status consistente; causa atual; tail e histórico sem duplicação |

Os testes de fault injection usam recursos próprios e nunca encerram processos
da sessão do usuário. Gates rápidos por milestone precedem a campanha integrada.
Comparações de desempenho usam distribuição e trabalho realizado, não um timeout
estreito que falhe apenas por carga da máquina de desenvolvimento.

## Fontes que orientam as decisões

- [Kubernetes controllers](https://kubernetes.io/docs/concepts/architecture/controller/):
  reconciliação de estado desejado/observado e controladores com responsabilidade pequena.
- [Erlang supervision](https://www.erlang.org/doc/system/sup_princ.html): isolamento
  de falha e orçamento de reinícios, sem cascata entre entidades independentes.
- [containerd runtime v2](https://github.com/containerd/containerd/blob/main/docs/runtime-v2.md):
  separação de controle e dono do processo; referência para o experimento de supervisor.
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects):
  contenção e observação do conjunto de processos, preservando as limitações da API.
- [Transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
  e [SQLite WAL](https://sqlite.org/wal.html): persistência, replay idempotente e
  limites reais de concorrência de escrita.
- [Temporal activities](https://docs.temporal.io/activity-definition): retries
  exigem idempotência; uma engine durável não torna efeitos externos exatamente únicos.
- [ACP session setup](https://agentclientprotocol.com/protocol/v1/session-setup):
  referência futura de negociação de capacidades; não é dependência deste plano.

Essas fontes sustentam padrões de arquitetura. Os critérios e a seleção de mudanças
acima são propostas específicas para o código e incidentes do Nexus.
