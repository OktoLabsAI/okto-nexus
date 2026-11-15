# HOME-R1 — fontes, autorização, correlação e invalidação

Paths relativos ao checkout; a leitura autoritativa está nas fontes atuais,
não na presença deste mapa. Nenhum GET Home chama Core/Connector por cartão.

| Origem / fonte | Permissão e correlação | Atualidade / sinal / recuperação |
|---|---|---|
| Handoffs; application/handoff_runtime_views.py e sqlite/handoff_runtime_views.py | Workspace autorizado; handoff_id e claim_epoch. Query existente é broadcast-only; a nova relação cobre também diretos. | Eventos de handoff e receipts invalidam work/results; prazo exige relógio/fallback. |
| delivery_outbox; migrations032/045/094/120 | delivery_id é a unidade lógica; handoff binding explícito faz o pai. Ligações atuais e tentativas históricas ficam distintas. | Mudanças de entrega/dispatch; não inferir execução de inbox unread. |
| execution_operations/receipts/sessions; migrations066/094 | Operador canônico; Server/executor/operação/sessão/geração. Sessão aberta e native accepted não são RUNNING. | Nem todo receipt gera events geral; snapshot, reconnect e fallback15s são obrigatórios. |
| execution_results; application/execution_results.py | Mesmo escopo e sequência terminal contígua; claim antigo não conclui claim atual. | Resultado durável e retenção; conteúdo completo sob demanda. |
| Attention; application/attention.py e sqlite/attention.py | authenticate(...require_feature=False), feature e preferências canônicas; attention_id/source_revision/preference_revision. | Stream Attention já tem reset/low watermark; next_change_at/next_refresh_at atualizam prazos. |
| Decisão nativa; attention_native.py / execution_native_facts.py | Destinatário, revisão, autoridade e validade atuais; operador não personifica agente destinatário. | Releitura fresca antes do efeito; CONFIRMED e aplicação nativa continuam separados. |
| Visto de resultado; attention_results.py | Episódio result_unseen compartilhado e revisão/CAS. Visto não é ACK. | Novo episódio/revisão reaparece; não usar watermark global. |
| Mensagens e artefatos; APIs atuais | Autorização da origem; agrupamento só por referência persistida. Não carregar payload completo na visão inicial. | Eventos de mensagem/resultados; download/preview lazy com proteção existente. |
| Agentes/presença; observability.py e tabelas atuais | Nós Graph globais não medem participação no projeto. Projetar vínculo ou atividade autorizada antes de contar. | Presença e conectividade são sinais próprios; expiry nunca vira idle presumido. |
| Externo; application/observations.py e sqlite/observations_repo.py | Fonte/instância/geração, vínculo explícito e workspace confiável. Sem workspace não entra no projeto por inferência. | observed_at/expiry, stale/off/disabled próprios; ausência não bloqueia Home. |
| Shell; App.tsx/useSSE/useAttention | Uma infraestrutura compartilhada; não abrir stream Home. Payloads são isolados por origem/identidade/workspace. | Snapshot inicial, onopen/reconnect/retention gap/tab resume provocam releitura limitada. |

## Controles a compor

AttentionInspection já delega aos componentes de Approval/Handoff/runtime,
MessageDetail e ExternalObservationInspection. Extrair seu corpo contextual e
manter as mesmas máquinas de estado; uma camada ativa e um guard de navegação.
Adaptar visto/adiado dos itens compactos ao mesmo endpoint/CAS, preservando o
controller da Attention para seus consumidores atuais.

MetaHarnessView contém o composer e anexos. Extrair essa composição para novo
pedido; continuidade usa RuntimeApi com sessão explicitamente validada, jamais
o agente/sessão mais recente. App preserva seleção, scroll e rascunho; 401/403
limpam dados protegidos e desautorizam ações.

## Fronteiras de snapshot e carga

O serviço Home abre um UoW de leitura, fixa o relógio e compõe as queries das
fontes no mesmo SQLite. AttentionService abre UoW próprio, então reutilizar a
porta snapshot e projeções, sem HTTP interno ou snapshots concorrentes. Nenhum
filesystem de artefato, journal integral ou provedor dentro da transação.
Contagens e páginas usam a mesma relação autorizada; não concatenar páginas para
fingir inventário completo. Medir queries por família, não por agente.
