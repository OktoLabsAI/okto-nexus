# Auditoria dos invariantes do plano

Esta revisão liga os dez invariantes à implementação e a cenários observáveis.
As evidências locais usam armazenamento e protocolos reais com providers
sintéticos. Não substituem T40, qualificação universal de harnesses ou a auditoria
de todas as fronteiras de commit em T24. A campanha instalada e os digests de
seus três wheels constam no ledger; só resultados terminais aprovados contam
como evidência, nunca o estado RUNNING de uma campanha.

| Invariante | Autoridade na implementação | Evidência específica e limite |
|---|---|---|
| INV-01 — claim canônico | `SqliteHandoffRepo.claim` faz UPDATE condicional por workspace/status OPEN e incrementa epoch. `HandoffRuntimeAttemptService.claim` chama o mesmo caso de uso dentro da UoW; agenda não altera a posse. | `test_handoff_broadcast_scale`: um claim/um grant/um envio entre cem agentes. `test_handoff_runtime_attempts`: resposta perdida recupera operação e epoch originais. |
| INV-02 — perdedores sem modelo | `runtime_handoff_notifications.queue` persiste a classificação competitiva e retorna antes do pipeline conversacional. `HandoffRuntimeProcessor` só consome admissão após obter a operação do claim. | `test_handoff_runtime_notifications`: broadcast fica na inbox/agenda sem outbox produtivo; direto continua executando. Escala conta chamadas nativas, não apenas respostas visíveis. |
| INV-03 — fila não é disponibilidade | Reserva técnica e `immediate_only` precedem claim automático. `SqliteCapacityAdmissionRepository.require_available` revalida a unidade exata. | Candidatos one-shot com pool/host cheio não criam chamada QUEUED nem claim; `test_handoff_last_slot` mantém a tarefa perdedora OPEN para MCP. |
| INV-04 — MCP-only elegível | A seleção técnica do scheduler consulta endpoints runtime; a elegibilidade canônica e a inbox MCP não dependem dessa seleção. | `test_mcp_only_agent_keeps_inbox_and_can_win_before_reserved_runtime` assume via MCP sem endpoint/ocupação e libera a reserva runtime perdedora. |
| INV-05 — identidade lógica única | `SqliteHandoffCandidateRepository.agents_page` usa UNION por agent_id; seleção de endpoint permanece no resolvedor de binding. Claim/epoch e `execution_tool_claims` não são transferíveis entre sessões. | Paginação deduplica endpoints; `test_handoff_executor_selection` usa dois Connectors e recusa ambiguidade; `test_reserved_handoff_tools` verifica vencedor MCP/native e recusa sessão irmã. |
| INV-06 — reserva não concede autoridade | `CapacityRequest` não inclui payload. Autorização é revalidada no claim/consumo/despacho. Leitura e conclusão gerenciadas exigem escopo e posse da sessão. | Testes de contrato rejeitam campos extras; `test_native_actions` cobre teto de ações, revogação, workspace e sessão; leitura pré-claim não entrega payload. |
| INV-07 — regras atuais preservadas | `HandoffCandidateDiscovery._eligible` reutiliza `filter_available_handoffs`; autorização de automação usa `execute_work` com grant/revisões. O claim canônico continua validando dependências, target, audiência e epoch. | Matriz de candidatos cobre dependência/audiência/opt-in/contrato; `revocation-audit.md` mapeia revogação entre assess, reserva, consumo, despacho e lease. Não se presume autorização a partir de observação AVAILABLE. |
| INV-08 — término nativo não conclui negócio | O vínculo de handoff mantém o resultado fora do relay conversacional; conclusão autenticada e modo estruturado explicitamente admitido continuam nos casos de uso canônicos. | `test_handoff_business_outcomes`: final nativo processado sem mensagem de relay, conclusão explícita única, VERIFYING e retrabalho no dono. `test_handoff_runtime_views` expõe pendência de decisão. |
| INV-09 — incerteza não permite replay | Journal Core impede substituir uma intenção existente pela recusa pré-abertura. Prova de não envio é distinta de resultado desconhecido; capacidade física só é liberada com confirmação. | Preopen recusa fatos nativos existentes/UNKNOWN; testes remotos preservam claim/epoch ao reconectar; `test_sender_commit_cuts` mantém SENDING como RECONCILING mesmo quando a resposta do commit se perde. Parada retida não libera slot por timeout. |
| INV-10 — fila explícita preservada | `immediate_only` é argumento da aquisição automática; pedidos explícitos continuam na modalidade que permite fila. Afinidade e gate de capacidade são compartilhados com mensagens normais. | `test_one_shot_handoffs`: segundo claim explícito fica QUEUED e recebe sessão distinta após liberação; erro da fila chega ao criador. `test_handoff_message_order` preserva FIFO; `test_handoff_ordinary_fanout` mantém respostas múltiplas. |

## Composição transacional e arquitetura

O caminho automático passa a mesma UoW por `claim_managed_in_transaction`,
`RuntimeWorkService.enqueue` e `admit_domain_delivery`. O
`DeliveryTransactionFactory` apenas devolve essa UoW: não abre conexão, não faz
commit e não chama host. Assim, claim/grant, mensagem/proveniência/causalidade,
delivery/binding, sessão/operações, afinidade, posse da ferramenta e admissão
lógica participam da transação externa. As chamadas ao host ficam em
reserve/consume/release fora dela. Testes de rollback no vínculo e na posse
da sessão exercitam a composição. A auditoria T24 consolidou
os participantes e as fronteiras de contenção em commit-boundary-audit.md.

Os novos coordenadores de agenda, descoberta, tentativas, capacidade, contenção,
liberação e recuperação pré-abertura dependem de ports. Adaptadores SQLite
persistem seus estados, e o bootstrap compõe implementações embedded/remotas.
Core recebe escopo técnico, sem regras de target ou eleição de handoff.
Connector transporta e reconcilia esse contrato usando APIs públicas do Core.
Os módulos legados de admissão/claim conservam SQL preexistente; esta revisão
não declara uma migração integral desses módulos para novos adaptadores.

## Conclusão local e validação posterior

T24 e as campanhas instaladas finais foram concluídos: Nexus 54, Core 187 e
Connector 99 testes aprovados, sem falhas/erros/skips. Os dez invariantes têm
evidência local; os limites dos providers sintéticos continuam explícitos.
O usuário adiou T40 em host independente para um teste conjunto posterior.
Nenhuma alteração na instância em uso, commit ou push foi realizada.
