# Reconciliação finita dos 28 invariantes

Proposta: 25 VERIFIED e 3 condicionais. Nenhum status foi alterado.

INV-06, INV-20 e INV-21 dependem do fechamento da qualificação Nexus SVC-07. Core/Connector têm evidência instalada própria; ela não substitui Nexus.

INV-12, INV-24 e INV-28 podem ser VERIFIED como regras de honestidade. Isso mantém M1/M2/R3 abertos e não executa nem promove login, reboot, provedor ou cadeia completa de cofre→cliente.

A matriz contém texto literal, linha do plano, fonte atual com SHA, testes/assertions e XML retidos, limite e motivo por ID. O parser validou os PASS citados; não rodou testes.

| ID | Proposta | Fundamento |
|---|---|---|
| INV-01 | VERIFIED | Identidade selecionada e autenticada permanece agent_id; sessões/instâncias e fontes têm seus próprios IDs auxiliares. |
| INV-02 | VERIFIED | Participante conecta diretamente ao MCP HTTP do Server; exportação/guia e observador não criam servidor MCP intermediário. O Connector mantém o canal R4 de execução. |
| INV-03 | VERIFIED | Boundaries retidos excluem dependências entre aplicações. Core recebe contratos/ports de execução, e o drain novo apenas metadata de runtime/journal. |
| INV-04 | VERIFIED | Claim, entrega e decisões permanecem serviços canônicos Server; Connector realiza a execução do binding autorizado via R4, sem inbox/handoff próprios. |
| INV-05 | VERIFIED | Projeção distingue estados e proveniência; publicação externa não toca coordenação/presença/capacidade e recibo recebido não vira liveness/idle. |
| INV-06 | CONDITIONAL_PENDING_QUALIFIED | Idle/done externos não liberam turno/reserva nem alteram prioridade/fairness; timeout de observação não cancela. Novo drain requer prova de quiescência ou força explícita e retém UNKNOWN. |
| INV-07 | VERIFIED | GET/inspeção e preferências são passivos sobre tabelas canônicas; decisões exigem controles existentes, autoridade e CAS. |
| INV-08 | VERIFIED | OBS publica somente estado auxiliar. Correlação é operador-only, prova nativa/OS não vem do cliente e não transfere autoridade ao sinal externo. |
| INV-09 | VERIFIED | Corridas MCP/runtime resultam em um único claim e efeito; inelegibilidade não muda com idle externo e MCP-only participa sem relatório externo. |
| INV-10 | VERIFIED | Recovery preserva request/operation/decisão originais; ausência/uncertainty não cria substituto e novo trabalho exige intenção explícita. |
| INV-11 | VERIFIED | Credenciais entram por mecanismos protegidos e referências; checkpoints/exportações omitem valores. Correção dos artefatos públicos foi revisada e itens sintéticos classificados. |
| INV-12 | VERIFIED | Contrato ParticipantClientConfig é distinto de capacidade/qualificação managed; cliente/build não observado fica UNKNOWN e generic/Pi não recebem adapter HTTP inventado. |
| INV-13 | VERIFIED | A central compõe fatos canônicos e guarda só preferências/anchors; observações/correlações são auxiliares e reads preservam tabelas canônicas. |
| INV-14 | VERIFIED | Schema fechado recusa campos de identidade/comando; texto de terminal é dado escapado e somente evento canônico pode concluir trabalho. |
| INV-15 | VERIFIED | CLI reutiliza ferramentas canônicas; schemas e descoberta validam parâmetros antes do efeito. Mudanças MCP têm medições de superfície retidas e teste de orçamento. |
| INV-16 | VERIFIED | Lifecycle compõe o mesmo Server/DaemonApp e os mesmos contratos Core, sem segundo scheduler, fila produtiva ou identidade de agente. |
| INV-17 | VERIFIED | Instância é derivada de home/DB/usuário e protegida por exclusão OS/generation antes de bootstrap. Alias/perfis não permitem dois owners dos mesmos dados. |
| INV-18 | VERIFIED | Topology é resolvida antes de lifecycle local; RemoteTarget apenas verifica Server remoto e não oferece fallback de início local. |
| INV-19 | VERIFIED | Start instalado usa o gerenciador nativo e não lança daemon avulso. Intent/lock existentes impedem concorrência e submissão repetida enquanto pendente. |
| INV-20 | CONDITIONAL_PENDING_QUALIFIED | Reuso/recovery não emite novos grants nem repete resultado incerto; leases antigas não migram na renovação explícita. Novo stop/restart mantém latch antes dos efeitos. |
| INV-21 | CONDITIONAL_PENDING_QUALIFIED | Saída do launcher/CLI mantém owner e trabalho; parada explícita fixa desired=draining antes da contenção. Direct IPC também precisa latch de supervisor. |
| INV-22 | VERIFIED | Readiness correlaciona owner/versão mas não afirma login/provedor/participação/trabalho. Doctor mantém checks/proof levels independentes. |
| INV-23 | VERIFIED | Status/log/doctor padrão são observações sem start/cofre/rede/inferência; connect de ação usa ensure_running somente após revisão/ação documentada. |
| INV-24 | VERIFIED | Relatórios distinguem saída de launcher, reinício sintético, login, logout/reboot e operação sem login; a campanha nativa preparada permanece não executada. |
| INV-25 | VERIFIED | Connect/init/work/decisões usam CLI e autoridade canônica vigente; fluxo padrão não exige dashboard e políticas preexistentes seguem obrigatórias. |
| INV-26 | VERIFIED | Preset é configuração versionada reutilizável, não identidade global. Finish/reconnect recuperam mesmo agente; merge só avança defaults não personalizados. |
| INV-27 | VERIFIED | Preset usa harness_settings vazio, tool_access=ask e grants limitados; modelo/instruções/sandbox não são sobrescritos. Merge preserva customizações e política nativa existente. |
| INV-28 | VERIFIED | Relatórios mantêm M1 incompleto quando há só serviço/sessão pronta; doctor não confunde initialize/readiness com tarefa, e trabalho terminal sintético é rotulado como tal. |

Limites comuns: Windows/local; pares sintéticos; provas históricas não se tornam reexecuções do código atual. Auditoria de import do Core 5721 permanece histórica; apenas imports do delta Core 140701 foram conferidos estaticamente.

A leitura não encontrou lacuna concreta adicional de produto nesses contratos. As três entradas condicionais são de qualificação em andamento, não uma declaração de falha. O parent decide a aplicação das recomendações e o aceite da evidência final.
