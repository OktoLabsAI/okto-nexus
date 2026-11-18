# Okto Nexus — sessões interativas na UI e no terminal
## Chat direto por sessão, próximo turno, reorientação explícita e detach sem interromper

**Plano:** SESSION-INTERACTION-R1 · especificação inicial consolidada · 17/11/2026  
**Destinatário:** Codex / agente de implementação com capacidade intermediária.  
**Estado:** requisitos de desenvolvimento. Inspeção estática de arquivos selecionados e documentação primária; não foram executados testes do Nexus, adaptadores ou provedores nesta elaboração.  
**Escopo obrigatório:** chat na sessão exata; mensagens nativas de usuário; fila durável para o próximo turno; steer explícito; comandos por capacidade real; `connect -i`/`--no-interactive`; pergunta final em TTY; attach/retomada posterior; continuidade ao fechar o terminal; local e remoto sob os mesmos controles.


**Dimensão:** 41 tarefas · 148 cenários de aceite · 24 requisitos · 8 etapas de implementação.

## Como usar este pacote

Este documento é autocontido para esta feature. Não é uma revisão incremental que dependa de outro plano Quick Connect ou Home para ser entendido. A implementação é incremental para permitir validação, mas todos os requisitos aqui definidos pertencem à mesma entrega. Reutilizar o que estiver pronto no checkout; não reconstruir a Home, o daemon ou a coordenação entre agentes.

Use `PROMPT_CODEX_NEXUS_SESSOES_INTERATIVAS_R1.md` como entrada. O Markdown define comportamento; `NEXUS_SESSOES_INTERATIVAS_LEDGER_R1.json` registra tarefas/testes; `MATRIZ_CAPACIDADES_SESSAO_R1.md` separa fatos observados de hipóteses a qualificar. Todos os novos testes começam em NOT_RUN. Não apagar evidências de outras frentes ou converter relato de teste antigo em PASS desta feature.

**Regra de produto:** a pessoa escolhe onde interagir, não quem executa. O executor durável mantém a sessão; navegador e terminal são superfícies de interação. Fechar uma dessas superfícies não encerra a sessão nem cancela seu trabalho.

---

# 1. Base consultada e delta concreto

## 1.1 Referências fixadas

| Componente | Referência consultada | Versão declarada / uso |
|---|---|---|
| Nexus Server/frontend/CLI | `feature/v0.3.7` · `8b4001fa1db17bf29d0c773eed3535e79fce70cb` | 0.3.7; Python >=3.11; pin Core 0.0.14. |
| Core | `feature/v0.0.14` · `497ee2b7a14b99c50cba97eac74f3b00d4863f26` | pyproject declara 0.0.14; observar que comentários/documentos podem conter números diferentes. |
| Connector | `feature/v0.0.13` · `a4d510080d7a685fa442a4c5c30419952589fe04` | pyproject declara 0.0.13 e pin Core 0.0.14; não inferir cronologia de todas as branches pelo número. |

A referência identifica código, não release publicado nem versão instalada pelo usuário. Conferir os três checkouts, instruções AGENTS.md/CI, wheel efetivamente vendorizado e respectivos hashes antes de alterar. Branch de Core declarando 0.0.14 não prova que seu conteúdo seja idêntico ao wheel pinado pelo Server. Não retornar automaticamente a esses SHAs nem aplicar reset/clean/force-push. [S01–S03]

## 1.2 Base existente que deve ser reaproveitada

| Evidência estática | Consequência normativa |
|---|---|
| `RuntimeOperations.tsx` já possui `runtime.start`, `turn.submit`, `turn.steer`, `turn.interrupt`, `runtime.close`, escopo exato, recuperação e revisão. | O composer é uma apresentação mais simples sobre ações canônicas, não mensagem no barramento Operator e não escrita direta no subprocesso. [S04] |
| `HomeEntryInspection.tsx` já resolve sessão e oferece continuação no contexto. | Evoluir esse painel em conversa + atividade técnica, sem novo menu ou tela independente. [S05] |
| `TerminalWork` usa intents, operações, recibos, identidade/escopo e decisões nativas. | Aproveitar essa admissão; `work resume` continua recuperação de envio, não vira attach nativo. [S06] |
| `terminal-work.md` já separa saída do observador de interrupt/close e mantém trabalho no serviço. | Estender a garantia ao terminal nativo real; não supor que ela existe ao iniciar um novo processo foreground. [S07] |
| `connect.py` já integra Quick Connect e parser extraído; no fluxo documentado, `--no-chat` evita prompt Nexus. | Preservar CWD/Git/ID do Harness, revisão e recibo; trocar somente a decisão da superfície de interação, com compatibilidade explícita. [S08] |
| Registry Core declara targeting/timing diferentes para Codex, Pi e Claude. | Não ter um único booleano genérico de “suporta comandos”; obter capacidade efetiva por instalação/sessão/estado. [S09] |
| Codex atual usa app-server por stdio; Pi usa RPC por stdio; Claude usa stream-json por stdio. | São protocolos estruturados, não terminais PTY anexáveis por definição. Habilitar attach exige integração adicional real. [S10–S12] |
| Comentário do adaptador Claude descreve steer como interrupt + reenvio e janela de recusa antes da geração. | “Reorientar” deve informar esse efeito e preservar o guard; não tratar como append não destrutivo. [S12] |
| Pi diferencia término de agente de estabilização; há sinais/correlação próprios da versão. | Fila não despacha por silêncio nem pelo primeiro evento terminal superficial. [S11, W04–W05] |

Nenhuma linha acima comprova operação real nesta elaboração. O baseline orienta arquivos e hipóteses de integração; novas campanhas são obrigatórias.

## 1.3 Relação com outras features

Preservar Home com Active/Needs You/Results e seus badges; nomes públicos ID do Harness; Quick Connect com projeto Git/CWD, colisões e confirmação; navegação simples e Advanced; runtime remoto pelo Connector; MCP HTTP direto no Server. Este plano não renomeia essas entidades nem reabre decisões de layout.

A regra nova de envio por sessão é deliberadamente **distinta** de `messages.send`/inbox/handoff. Ambas continuam existindo: mensagens de coordenação entre agentes ficam no barramento, e esta entrada humana é entregue como entrada nativa à sessão selecionada. Interações geradas pelo modelo não ganham a autoridade humana de quem abriu a UI.

---

# 2. Decisões fechadas e definições

## 2.1 Contrato com o usuário

1. Na tela já existente de uma sessão há histórico de conversa, atividade, estado e campo para escrever como usuário daquele harness.
2. Se a sessão puder começar um turno e não houver entrada anterior na fila, Enviar entrega a mensagem. Se estiver ocupada, a mensagem fica aguardando o próximo turno elegível.
3. Reorientar agora é uma ação explícita separada. Nunca transformar Enviar em steer por conveniência do adaptador.
4. A UI lista comandos conhecidos do harness e distingue suportado, temporariamente indisponível, somente na interface nativa e não suportado.
5. O Connect pode abrir a interface nativa no próprio terminal ou terminar somente com a conexão. Sem opção, pergunta ao final quando houver terminal interativo.
6. A escolha inicial não impede abrir a sessão mais tarde, nem continuar pela UI depois de desanexar o terminal.
7. Fechar janela, perder o transporte de attach ou desanexar só remove a superfície. A execução e a fila admitida continuam sob o dono durável, dentro das autorizações vigentes.
8. Interromper é ação explícita da UI (e de controles CLI já existentes), não efeito colateral de fechar a interface.
9. Mesma conexão/ID do Harness não significa mesma sessão; selecionar sempre o contexto exato. Não usar “latest”, CWD ou nome de processo para adivinhar.
10. Não oferecer um prompt Nexus como se fosse a TUI nativa do Codex/Pi/Claude. Um chat Nexus no terminal é uma superfície válida, mas diferente e identificada.

## 2.2 Vocabulário normativo

| Termo | Definição neste plano |
|---|---|
| Mensagem nativa de usuário | Conteúdo entregue ao protocolo/API do harness com papel de usuário na sessão exata; ator auditável continua humano autenticado. |
| Turno produtivo | Ciclo completo de trabalho do harness, incluindo chamadas de ferramentas e etapas automáticas que pertencem àquela execução. Não é cada fragmento de texto nem cada chamada isolada ao modelo. |
| Próximo turno elegível | Primeira oportunidade confirmada após o turno anterior terminar/estabilizar, sem tool/approval pendente, controle em trânsito, ownership incerto ou bloqueio de política. |
| Fila de entrada da sessão | Intenções duráveis de usuário ainda não entregues ao harness, subordinadas à admissão de execução existente. Não é inbox de agente nem outro scheduler de tarefas. |
| Steer | Reorientação explícita de um turno identificado, com a semântica efetiva do adaptador. Pode ter timing de fronteira ou composição interrupt+send; deve ser descrito. |
| Attach vivo | Abrir uma superfície sobre a mesma engine/processo/sessão corrente, sem reinício, clone ou fork. |
| Resume salvo | Reabrir a conversa nativa persistida após o processo terminar, quando suportado; não é attach ao processo antigo. |
| Transferência segura | Troca de driver/owner num ponto comprovadamente seguro, com checkpoint e fencing, somente quando não existe attach vivo compatível. Não aborta trabalho para satisfazer attach. |
| Detach | Encerrar somente o vínculo de apresentação/interação; não enviar interrupt, EOF ao worker, close ou kill. |
| Close | Encerramento explícito da sessão/runtime, diferente de sair do painel/terminal. |
| Leitor / escritor de terminal | Cliente anexado para observação / cliente autorizado a enviar eventos de entrada da interface nativa. A lease de terminal não é a lease de execução. |

## 2.3 Invariantes

- Um único dono executa e escreve a sessão nativa. UI, terminal e coordenação não criam processos concorrentes contra o mesmo transcript.
- Envio comum, reorientação, interrupt, resposta de aprovação, troca de modelo e close são intenções distintas, registradas e autorizadas separadamente.
- Busy/idle é derivado de sinais qualificados e atuais. Ausência de tokens, heartbeat do browser, timeout ou fechamento do terminal não comprovam idle.
- Mensagem aceita na fila não é mensagem consumida pelo modelo. ACK do protocolo não é turno concluído. Decisão registrada não é aplicada.
- Identidade humana de autenticação/auditoria não muda o agente destinatário. Não personificar agente para obter ferramentas ou responder pedido destinado a outro agente.
- IDs, revisões, geração da sessão, epoch do owner, target-turn e resultado incerto são preservados até a borda do efeito.
- A fila e controles continuam funcionando sem navegador/terminal. Não guardar a única cópia das mensagens aceitas em memória React, localStorage ou arquivo de perfil CLI.
- Capability de attach não concede acesso ao engine inteiro, a outros threads, filesystem ou provedor.
- Reabrir uma interface não renova grants, reenvia pedidos, aprova ferramentas ou altera modelo/root.
- Fechar uma interface não pausa a fila. Pausar/retomar fila é um controle explícito distinto.
- Terminal nativo mantém sua identidade visual/comandos reais, mas não pode ser uma porta de bypass dos controles do Nexus.

## 2.4 Requisitos rastreáveis

| ID | Tema | Requisito obrigatório |
|---|---|---|
| SI-R01 | Chat contextual | Evoluir o painel existente da sessão, com conversa, atividade e composer, sem novo menu ou sessão escolhida por recência. |
| SI-R02 | Entrada humana nativa | Enviar conteúdo como usuário nativo da sessão exata; preservar auditoria humana e não usar inbox/mensagem Operator/handoff para esse transporte. |
| SI-R03 | Histórico verificável | Projetar eventos reais com IDs, deltas/snapshots, origem, lacunas, retenção e autorização; sem conversa fictícia ou raciocínio privado. |
| SI-R04 | Próximo turno por padrão | Enviar enquanto ocupado cria entrada durável para o próximo turno elegível; idle comprovado pode despachar imediatamente respeitando FIFO. |
| SI-R05 | Fila durável e única | Ordenação por sessão, limites, cancelamento seguro, recuperação e integração ao árbitro atual, sem duas filas entregando o mesmo input. |
| SI-R06 | Steer explícito | Ação separada, alvo do turno congelado, efeito/timing por harness e promoção atômica de item pendente; sem fallback automático para novo turno. |
| SI-R07 | Interrupção segura | Interrupt explícito na UI aplica barreira de fila, mira o turno exato e não fecha sessão; retomar fila é outra ação. |
| SI-R08 | Comandos por capacidade | Catálogo versionado de subset nativo/Nexus, argumentos, efeito, disponibilidade por estado/política e evidência da instalação. |
| SI-R09 | Comandos não suportados | Avisar e preservar texto; não converter slash, skill, template ou shell em prompt/execução sem intenção/semântica literal comprovadas. |
| SI-R10 | Connect com modos | -i/--interactive abre nativo; --no-interactive só conecta; sem flag pergunta ao final em TTY; scripts não recebem prompt. |
| SI-R11 | Retomada posterior | Permitir listar/selecionar/attach e resume salvo depois, independente da escolha inicial; work resume conserva recuperação de envio. |
| SI-R12 | Nativo verdadeiro | Não simular TUI nativa com prompt Nexus; qualificar integração real Codex/Pi/Claude preservando a mesma sessão/engine quando vivo. |
| SI-R13 | Detach preserva trabalho | Fechamento/perda do cliente somente desanexa; dono durável drena I/O e mantém execução/fila sob autoridade vigente. |
| SI-R14 | Continuidade de identidade | Mapear conexão, sessão runtime, sessão nativa, geração e contexto exatos; sem fork/clone/latest disfarçado de retomada. |
| SI-R15 | Ownership e arbitragem | Um owner nativo e um escritor bruto; entradas UI/terminal/coordenação serializadas com fences, sem bypass por token/PTY. |
| SI-R16 | Autoridade em cada efeito | Revalidar pessoa, sessão, binding, grant, geração, comando, decisão e attach/takeover; revogação não reatribui trabalho. |
| SI-R17 | Local e remoto | Server coordena, Core executa e Connector hospeda; acesso humano remoto não usa chave de agente como credencial de operador. |
| SI-R18 | Privacidade e isolamento | Segredos no host/canais protegidos; sem tokens em argv/URL; terminal/Markdown/artefatos não ampliam escopo ou executam conteúdo não confiável. |
| SI-R19 | Compatibilidade | Preservar Quick Connect, Git/CWD, ID do Harness, perfis, --no-chat, comandos work, hashes/recibos e consumo dos componentes atuais. |
| SI-R20 | Capacidade comprovada | Separar doc upstream, capability declarada, instalação observada e qualificação real por versão/OS/mode; não anunciar paridade genérica. |
| SI-R21 | Estado/UX consistente | Fila não é execução, detach não é desconexão do Nexus, decisão não é retomada; foco/rascunho/scroll e Home permanecem corretos. |
| SI-R22 | Recuperação sem replay | Intenção durável e correlação na borda do efeito; entrega desconhecida bloqueia duplicação, restart não repete teste/turno/grant. |
| SI-R23 | Plataformas e sinais | Qualificar terminal real/PTY/ConPTY/process tree, clientes lentos e falhas; não prometer sobrevivência a logout/reboot sem prova própria. |
| SI-R24 | Gates e pacote | Testes por camada, campanhas consentidas, migração e rollback com filas pendentes; entrega final com limitações e evidências rastreáveis. |

---

# 3. Experiência da sessão na UI

## 3.1 Local e estrutura

Evoluir o painel contextual que se abre pela Home/Conversas. Nenhum menu adicional. Uma camada ativa, maximização sem modais aninhados; fechar devolve foco e scroll à Home. Sessão única inequívoca abre diretamente; múltiplas sessões exigem seleção, usando projeto, objetivo, harness, host e estado legíveis.

Cabeçalho: ID do Harness, harness real, projeto, host e sessão (ID curto com detalhe/cópia). Mostrar estado operacional, atualidade e terminal anexado quando houver. Abaixo, duas visualizações do mesmo contexto: **Conversa** como padrão e **Atividade técnica** para eventos/recibos. Não exibir transcript técnico bruto como se cada linha fosse uma fala.

Rodapé: composer, ação primária Enviar e ação separada Reorientar agora, controles de comandos e de interrupção. Fila compacta próxima do composer, expansível; não criar outra coluna de tarefas na Home.

Exemplo com sessão ocupada:

```text
reviewer · Claude Code · projeto API · neste computador
Executando · terminal anexado (mesma sessão)

[histórico de usuário, respostas e ferramentas recolhidas]

2 mensagens aguardando o próximo turno   [Ver fila]
[ Escreva para esta sessão...                         ]
[Adicionar ao próximo turno] [Reorientar agora ▾] [/ Comandos]
[Interromper execução]
```

O texto do botão muda de Enviar para Adicionar ao próximo turno quando o estado atual está comprovadamente ocupado. A decisão definitiva é do Server, porque pode haver uma corrida entre render e clique. Uma resposta pode indicar que a mensagem foi enfileirada apesar de a UI tê-la mostrado como pronta, sem perder o conteúdo ou disparar steer.

## 3.2 Entrada, rascunhos e identidade

A mensagem que aparece para o harness tem papel nativo de usuário; o payload não inclui um wrapper fictício “operator enviou mensagem via Nexus”. Metadados de origem/autor são guardados fora do conteúdo visível ao modelo, salvo metadados nativos que o contrato realmente permita. Não enviar por `messages.send`, não gravar inbox, não criar handoff implícito.

O Server registra `initiated_by` humano, `surface=web|nexus_cli|native_terminal`, destinatário canônico e intenção. Reutilizar o RequestContext e regras atuais. O termo humano/usuário é de apresentação; não retirar auditoria por o usuário ter distinguido isso do canal Operator.

Enter envia conforme preferência atual acessível; Shift+Enter cria linha; durante composição IME Enter não envia. Botão Reorientar não é acionado por Enter comum. Manter rascunho por sessão exata em memória; troca de sessão com rascunho pede confirmação. Não transferir texto entre sessões automaticamente.

Abrir painel/ler transcript é somente leitura. Digitado mas não enviado não entra na fila, no histórico canônico nem na engine. Depois do aceite durável, fechar a UI não perde a mensagem. Em erro de rede após envio, conservar referência da intenção e consultar resultado antes de permitir reenviar.

## 3.3 Histórico estruturado

Projeção de conversa normaliza somente eventos realmente disponíveis: usuário, resposta do assistente, chamada/resultado de ferramenta, estado do sistema, pedido humano, controle aplicado e limite de histórico. Ferramentas recolhidas; dados sensíveis seguem a política atual. Não expor raciocínio privado ou inventar mensagens para preencher lacunas. Resumos de raciocínio já publicados e autorizados podem aparecer numa seção identificada, nunca como resposta principal.

Distinguir evento nativo textual, delta acumulativo e snapshot. IDs devem incluir namespace completo e item/content-index apropriado; texto igual não deduplica duas mensagens legítimas. Associar a mensagem de usuário enviada ao eco nativo por ID/correlação comprovada. Se a versão não produz eco/ID suficiente, conservar o registro da submissão como tal, sem fabricar evento nativo.

Ferramentas/deltas de subagente permanecem no contexto do subagente quando a origem for conhecida; não atribuir toda saída ao assistente principal. Histórico paginado, cursor/epoch/retention-gap explícitos; reanexar não reinicia render do transcript inteiro. Quando o nativo não expõe o histórico anterior, mostrar “histórico anterior não disponível nesta integração”, sem afirmar que a sessão está vazia.

Fila não aparece como mensagem já recebida pelo modelo. Uma bolha provisória traz **Na fila**, **Enviando**, **Aceita pelo harness** ou **Envio não confirmado**. O resultado final é correlacionado com o turno correto, não com “a última resposta”.

---

# 4. Admissão e fila para o próximo turno

## 4.1 Caminho único de escrita

Introduzir um coordenador de interação por sessão no Server, ou estender a fronteira equivalente existente. Ele recebe entradas da UI/CLI, persiste intenção, aplica autorização e ordenação e encaminha pelos serviços canônicos de runtime. Core mantém execução/recibos; Connector transporta/hospeda; UI não agenda trabalho.

Antes de criar tabela, auditar intents/operations/outbox atuais: se já comportam admissão diferida e cancelamento seguro, estender esse contrato. Caso contrário, adicionar estrutura auxiliar de **intenção de entrada**, vinculada 1:1 à operação quando despachada. Não duplicar o texto em filas de coordenação nem criar um segundo runtime. A decisão de armazenamento é registrada na primeira etapa, preservando as regras abaixo.

`submit(mode=next_turn)` é o padrão. Todo input tem `client_intent_id` estável gerado antes do primeiro POST e fingerprint de conteúdo/escopo/modo. Novo ID a cada tentativa de rede é proibido. Admissão durável deve preceder confirmação na UI; armazenamento indisponível é recusa, não fila em memória.

## 4.2 Ordem e fronteira de turno

FIFO por sessão canônica. Ordem é `enqueue_sequence` monotônica atribuída transacionalmente no Server, não relógio do browser. Uma mensagem por turno, salvo pedido de composição explícito que não faz parte desta entrega. Não concatenar vários prompts automaticamente.

Enviar enquanto idle e sem predecessores/control barriers permite despacho imediato pelo caminho normal. Enviar enquanto ocupado ou com fila anterior insere no fim. O despachante só libera o próximo depois de:

1. confirmar encerramento/estabilização da execução corrente;
2. confirmar ausência de aprovação/ferramenta pendente que impeça progresso;
3. revalidar a sessão, geração, binding, owner, capabilities e autoridade do autor;
4. respeitar barreiras de interrupção, manutenção ou transferência de superfície;
5. reservar a capacidade canônica de forma atômica e persistir a mesma operação antes do envio.

O final de uma chamada ao modelo não basta se o harness continua processando ferramentas, retry, compaction ou follow-up interno. Para Pi, conferir `agent_settled` na versão qualificada; o atual contrato distingue esse ponto. Não usar sleeps como prova. [S11, W04]

UI/CLI usam a fila do Nexus. **Não enfileirar a mesma entrada também com um `follow_up` nativo e depois reenviar quando ficar idle.** Delegação da fila ao harness só é aceitável se o adaptador comprovar IDs, cancelamento, consulta, recuperação e ordem; a decisão padrão é uma única fila durável no Server com despacho quando pronto.

## 4.3 Estados observáveis e transições

| Estado auxiliar | Significado | Próximas saídas |
|---|---|---|
| `QUEUED` | Entrada durável aguardando elegibilidade | DISPATCHING, CANCELLED, BLOCKED_AUTH, PAUSED, EXPIRED, BLOCKED_SESSION |
| `DISPATCHING` | Slot/operação reservados; protocolo pode já ter recebido | ACCEPTED_NATIVE, REFUSED_BEFORE_SEND, DELIVERY_UNKNOWN |
| `ACCEPTED_NATIVE` | Aceite comprovado; não é conclusão | Turno/resultado via operação canônica; não retomar como fila |
| `REFUSED_BEFORE_SEND` | Recusa comprovada antes de escrita | Reavaliar somente com condições verificadas; registrar tentativa; não mudar intenção |
| `DELIVERY_UNKNOWN` | Possível efeito sem confirmação | Reconciliação pela mesma referência, nunca resend automático |
| `BLOCKED_AUTH` | Autoridade atual não permite despacho | Revisão humana/recuperação autorizada; sem grant automático |
| `BLOCKED_SESSION` | Sessão indisponível/encerrada ou mapa inconsistente | Diagnóstico; nova sessão somente por ação explícita |
| `PAUSED` | Fila retida por controle explícito/barreira | Retomada explícita; não apagar mensagens |
| `EXPIRED` | Prazo de entrada venceu antes de envio | Revisão explícita, não envio tardio silencioso |
| `CANCELLED` | Removida antes de fronteira irreversível | Terminal; não afeta o turno corrente |

Não duplicar estados produtivos SUCCEEDED/FAILED/CANCELLED na fila. O item referencia a operação que carrega o desfecho. `delivery_status` e `turn_status` aparecem separados.

Proposta de limites iniciais: até 50 entradas pendentes por sessão, texto até min(64 KiB UTF-8, limite atual de runtime/adaptador), TTL de pendência 24h. São defaults a documentar/configurar no mecanismo existente, não licença para truncar. Exceder limite recusa a nova entrada com motivo; mensagens aceitas não somem. TTL vencido segura a entrada; não demonstra que uma entrega incerta não aconteceu.

## 4.4 Concorrência, fairness e recuperação

O mesmo árbitro de sessão deve participar da admissão de turnos vindos do barramento de agentes, da UI e do terminal. Não alterar a semântica de inbox/claim; impedir que dois caminhos admitam turnos incompatíveis ao mesmo tempo. A política inicial é serialização por sessão e ordenação de entradas humanas pelo commit de aceite. Prioridade de controle (interrupt/steer) é explícita e não preempta automaticamente por ter origem humana. Registrar a integração com a fila de trabalho atual para impedir starvation silenciosa.

Após restart do Server, reconciliar operações possivelmente enviadas antes de liberar a fila. Somente itens comprovadamente não enviados podem voltar a ser despachados automaticamente. Restart não reabre sessão fechada nem repete trabalho incerto. Connector não cria fila produtiva paralela durante desconexão; comandos recebidos continuam sujeitos a leases/epochs atuais.

Lease/grant expirado: a entrada permanece visível bloqueada. Não emitir grant novo, mover mensagem para sessão nova nem mudar o autor. Se o contrato atual não permite renovar a sessão, explicar essa limitação e oferecer copiar o conteúdo para um novo pedido revisado, sem enviar automaticamente. [S07]

Dois clientes enviando ao mesmo tempo recebem ordem determinística. Client retry idêntico retorna mesmo item; payload diferente com mesmo ID retorna conflito. A consulta de status é passiva. Nenhum heartbeat de viewer mantém autorização produtiva artificialmente.

## 4.5 Cancelar uma mensagem na fila

Permitir Remover da fila somente antes do envio irreversível, com `expected_revision`. Corrida entre cancelar e despachar tem um único vencedor. Se já houve envio possível, a UI explica e permite inspeção/interrupt explícito; não mostra “removida” indevidamente.

Não implementar reorder ou edição in-place de conteúdo já aceito neste recorte. Para corrigir mensagem ainda em fila, remover com CAS e enviar outra intenção. Rascunho local pode ser editado normalmente. Estado unknown não pode ser apagado para liberar uma nova tentativa.

---

# 5. Reorientar agora e interromper

## 5.1 Reorientação explícita

Reorientar agora é separado do envio normal e exige capacidade efetiva para o turno atual. A UI mostra o efeito antes de confirmar quando houver interrupção ou mudança de turno. Não manter o modo Reorientar selecionado como default para mensagens seguintes.

| Adaptador do baseline | Semântica observada no código | Exigência de UI/controle |
|---|---|---|
| Codex app-server | Target nativo obrigatório para steer; registry indica imediato. | Fixar expected turn ID e revalidar na escrita; se o turno mudou, recusar em vez de reorientar outro. |
| Pi RPC | Steer direcionado ao run corrente, com entrega em fronteira. | Rotular “Reorientar na próxima fronteira disponível”; ACK/queue_update não prova consumo. |
| Claude stream | Registry indica imediato; implementação descreve interrupt + resend e janela insegura antes da geração. | Avisar “Interromper o turno atual e reorientar”; exigir consentimento e respeitar a janela de recusa, sem loop cego de retry. |

São fatos do código consultado, não garantia universal de versões instaladas. Capabilities efetivas e campanhas são a fonte do estado habilitado. [S09–S12]

Se uma mensagem já enfileirada for escolhida para reorientação, fazer promoção atômica QUEUED→controle, com ID original preservado e operação de controle derivada. Ela não pode permanecer elegível para envio futuro e ser enviada também como steer. Se já estiver em dispatch ou com resultado incerto, recusar promoção. Recusa comprovadamente antes de envio pode conservar o item na fila com seu modo anterior, mas não executar outra ação silenciosamente.

Se o turno terminar durante o clique, não converter steer em novo prompt automático. Manter o texto e pedir a intenção correta. O nativo pode não possuir ID de turno: nesse caso o host precisa comprovar a geração do run na borda da escrita; se não puder, a ação é indisponível, nunca dirigida ao “run que aparecer”.

## 5.2 Interrupção explícita

O botão Interromper usa a sessão/turno selecionados, sem fechar runtime ou outras sessões do agente. Antes de despachar o interrupt, instalar barreira durável de drenagem da fila dessa sessão. A fila pendente fica **pausada**, não apagada. Assim um novo turno não começa imediatamente após o usuário clicar em parar.

Uma corrida em que o turno termina antes do interrupt não permite que o comando atinja o próximo turno. O control target e a barreira devem estar alinhados à mesma geração. Se a API legada admite `current_run`, acrescentar a condição segura na nova fronteira em vez de manter comportamento ambíguo.

Após interrupção confirmada, a UI mostra o turno interrompido e “N mensagens pendentes, envio pausado”. Retomar fila é ação explícita, autorizada e revalidada. Recusa de interrupt não remove silenciosamente a barreira; a UI explica se o turno segue vivo e mantém decisão humana. Fechar o painel não equivale a essa ação e não cria a barreira.

Responder a aprovação ou pergunta usa seu endpoint canônico e destinatário apropriado. Digitar “sim”, “pode executar” ou “aprovo” no chat não responde à decisão estruturada.

---

# 6. Catálogo de comandos por harness

## 6.1 Contrato

O Server expõe uma projeção versionada por sessão: comando, label, argumentos tipados, descrição do efeito, executor handler, suporte por superfície, estado de disponibilidade, motivo e exigência de confirmação. A origem é metadata confiável do adaptador/versão mais autorização/configuração atuais. Não importar comandos arbitrários enviados pelo modelo.

Estados mínimos: `supported`, `disabled_for_state`, `denied_by_policy`, `native_only`, `unsupported`, `unqualified`. Native-only não garante que a instalação presente tem o comando; mostrar versão/motivo conhecidos e não lançar outra sessão para tentar.

O subset inicial obrigatório é o que pode ser provado: ajuda/capacidades, estado da sessão, envio para próximo turno, steer quando qualificado e interrupt. Ajuda/estado gerados pelo Nexus precisam ser identificados como ações Nexus, não comandos nativos inventados. Compactar contexto, escolher modelo, esforço, exportar, fork, clear, resume e extensões só entram como supported quando houver handler tipado, persistência/autoridade e testes. O restante aparece com limitação explícita.

Não encaminhar todo texto iniciado por `/` ao stdin como se fosse uma mensagem. Prefixos nativos (`/`, `!`, templates/skills, atalhos) podem executar comandos e não texto comum. O parser separa intenção de comando de intenção de texto. Comando desconhecido: mostrar aviso, preservar rascunho, não enviar. Oferecer “Enviar como texto” somente se o adaptador possuir mecanismo literal provado; não assumir que `//` escapa em todos os harnesses.

Não aplicar heurística que converta caminhos como `/tmp/file` em comandos suportados. Uma escolha explícita de envio literal precisa impedir expansão de skill/template pelo protocolo quando aplicável. Onde não há mecanismo literal seguro, informar a limitação em vez de prometer literalidade.

## 6.2 UX e segurança

Ao digitar `/`, lista com busca e documentação curta do que funciona nessa integração. Um item indisponível explica por quê e o que fazer. Selecionar comando não executa automaticamente; confirmar ação com argumentos, principalmente alterações destrutivas, política, modelo ou controle.

Não expor comando de shell arbitrário, update/install/login/logout, mudança de permissão global ou acesso ao cofre pela nova API de comandos. Comandos native-only de administração continuam sob o modelo de segurança da superfície nativa e precisam ser avaliados no gate de attach; não anunciar controle granular no Nexus enquanto um túnel irrestrito o contorna.

Mudança de modelo/configuração/branch/conversa, quando futuramente suportada, produz revisão/capability nova, preserva filas vinculadas ao contexto anterior e revalida próximas mensagens. Nada de mover uma fila do thread A para B porque o usuário executou `/resume` na TUI.

---

# 7. CLI: conectar, escolher a superfície e abrir depois

## 7.1 Flags propostas

```sh
okto-nexus connect codex my-project --id builder -i
okto-nexus connect pi my-project --id tester --interactive
okto-nexus connect claude my-project --id reviewer --no-interactive
okto-nexus connect codex
```

`-i` / `--interactive`: após conexão concluída, solicitar abertura da **interface nativa** no terminal atual. A palavra interactive qualifica somente a superfície pós-connect: `--no-interactive` não significa aceitar automaticamente revisões nem proibir perguntas de setup em TTY; scripts usam o contrato JSON/não TTY existente. `--no-interactive`: concluir conexão sem abrir TUI nem prompt Nexus. Não usar `-ni`: é ambíguo com opções curtas compostas; a flag longa é o contrato desta entrega. Reconhecer erro comum e orientar, sem aceitá-lo por abreviação.

Sem flag em TTY: depois do recibo positivo, perguntar **“Abrir o <harness> neste terminal? [s/N]”**. Escolher Não só retorna ao shell. Não iniciar automaticamente o prompt `work` nesse caminho novo. O prompt Nexus continua acessível explicitamente por `okto-nexus work`; não é eliminado nem apresentado como TUI nativa.

O `--no-chat` legado permanece equivalente a não abrir interface pós-connect e com aviso de ajuda quando pertinente. `--no-chat` com `-i`, ou positivo e negativo juntos, é erro antes de efeitos. Um nome de sessão/ID de conexão não é uma opção de controle de terminal.

## 7.2 Tabela de comportamento

| Invocação | Efeito após setup |
|---|---|
| `connect ... -i`, TTY, capacidade qualificada | Abrir sessão exata ou oferecer seleção se houver várias; não enviar tarefa por abrir. |
| `connect ... --no-interactive` | Não abrir superfície; retornar ID/estado e comando seguro para attach posterior. |
| `connect ...` em TTY | Pergunta final, default Não. |
| `connect ... --json` ou stdin/stdout não TTY | Nunca perguntar; conectar somente; incluir capacidade e `attach_argv` quando apropriado. |
| `connect ... -i --json` ou sem TTY | Erro de combinação antes de setup, sem tentar abrir console oculto. |
| `connect ... -i --plan` | Apenas registrar intenção de apresentação no plano; sem abrir serviço por causa disso, sessão ou terminal. Regras plan existentes continuam. |
| `connect ... --approve R` com escolha de superfície já revista | Aplicar efeitos da revisão; a escolha de abrir não amplia grant nem muda identidade. |
| Attach falha após conexão confirmada | Preservar sucesso da conexão e retornar pós-ação indisponível/falha; não desfazer identidade/binding nem repetir setup. |

A pergunta final de superfície não é uma segunda confirmação idêntica de setup. O setup aprova configuração/teste; abrir uma sessão produtiva vazia pode precisar de admissão própria. Se for um efeito adicional, explicar e usar a autoridade existente, sem um novo turno pago ou prompt de teste oculto.

`--no-interactive` não exige criar sessão vazia para “estar pronto”. O harness pode ser aberto sob demanda pelo pedido feito na UI, ou por attach posterior que inclua uma abertura explicitamente autorizada. O teste temporário do Connect não se torna sessão de trabalho por conveniência. Políticas one-shot, prazo de sessão e encerramento por segurança continuam valendo. Ao abrir, indicar se o contexto permite conversa persistente ou se termina após uma operação; não mudar a política do binding para manter uma janela viva. Para uma sessão encerrada pela política, usar retomada salva explícita quando suportada, sem afirmar que o processo antigo sobreviveu. O usuário não precisa abrir o dashboard para realizar essa escolha/revisão.

## 7.3 Comandos de sessão propostos

```sh
okto-nexus session list --id reviewer
okto-nexus session attach --id reviewer --session-id <ID_EXATO>
okto-nexus session attach --id reviewer
okto-nexus session resume --id reviewer --session-id <ID_EXATO>
```

Usar um subcomando singular `session` salvo equivalente já existente, documentando o mapeamento. `attach`: sessão viva, não recovery de envio. `resume`: contexto persistido comprovado depois de processo encerrado, só por ID exato e contrato qualificado; nunca `--last`. O comando deve explicar se vai anexar, esperar fronteira segura ou reabrir contexto salvo. `work resume` mantém seu significado histórico de recuperar uma submissão incerta. [S07]

ID do Harness seleciona conexão no workspace/Server; sessão seleciona contexto. Uma única candidata só pode ser selecionada automaticamente se catálogo completo e inequívoco, com escopo exposto. Com várias, escolher; sem TTY, erro estruturado. Candidata indisponível não é substituída por uma nova ou pela mais recente.

Resume salvo sem evidência nativa suficiente é recusado de forma honesta. Se o protocolo exige novo ID de sessão runtime, registrar sucessora e linhagem explicitamente, reter a sessão histórica e pedir confirmação; não chamar isso de “mesmo processo” ou usar fila antiga na nova sessão silenciosamente. Para attach vivo, a exigência é a mesma sessão e a mesma execução, sem interrupção.

## 7.4 Saída e códigos

Preservar códigos legados existentes; definir um envelope aditivo `interaction` com `requested_surface`, `resolved_surface`, `status`, `scope`, `attachment_id`, `attach_strategy`, `capability_revision` e motivo. Saída positiva do connect permanece distinta de `attached`. JSON não contém bytes ANSI nem token de attach; um secret é entregue por canal protegido/env/FD do cliente local quando estritamente necessário.

Antes de anexar, mostrar sessão/projeto/host e como desanexar. Depois do detach, retornar ao shell com mensagem “Sessão continua no Nexus”, link/comando sem segredos e referência exata. Não reexecutar connect para reencontrar o contexto quando attach falhar.

---

# 8. Terminal nativo e ownership durável

## 8.1 Arquitetura obrigatória

```text
Navegador / CLI Nexus / frontend nativo
       | autenticação humana + alvo exato + capacidade limitada
       v
Server: interação da sessão / admissão / fila durável / auditoria
       | operações e controles canônicos com geração/lease
       v
Host executor: Server local ou Connector remoto
       | Core + único owner nativo + bridge de interação/attach
       v
Engine/processo da sessão
```

O processo da engine não pertence ao shell do usuário. Para TUI com engine integrada, o host mantém master PTY/ConPTY e o processo; o CLI anexa um transporte de entrada/saída. Para engine com frontend separado, o host mantém a engine e o CLI inicia apenas o frontend contra o endpoint limitado. Nenhum dos casos é resolvido com `subprocess.run(harness)` filho do terminal nem com `nohup` sem contrato de processos.

Não confundir esta ponte com MCP no Connector: MCP Nexus continua HTTP no Server. O transporte de terminal é outro contrato de interação limitado por sessão. Não abrir porta pública de app-server/TUI ou expor Named Pipe/Unix socket a usuários não autorizados.

## 8.2 Estratégia preferencial e sequência de decisão

1. **Frontend nativo anexável ao engine existente:** preferir quando o harness oferece protocolo e seleção exata comprovados. Mediar métodos/entradas e observar a mesma sessão.
2. **Sessão nativa hospedada pelo executor com bridge semântico:** usar TUI/SDK/extension APIs suportadas, dono durável do PTY e eventos estruturados. UI envia pelo bridge, não por simulação de teclas para prompts automáticos.
3. **Transferência segura no limite do turno:** somente quando necessária e provada. Esperar término/estabilização, confirmar persistência, drenar efeitos, pausar dispatch, trocar owner com fence e abrir o MESMO contexto nativo. Não matar ferramenta/turno para atender pedido de attach. A fila preserva seus IDs e ordem.
4. **Indisponível:** se não houver caminho qualificado, retornar motivo preciso e manter execução. Um prompt Nexus alternativo pode ser oferecido explicitamente, nunca como sucesso nativo. A ausência não é aceitável para marcar a meta de attach daquele harness como concluída.

**Não basta** abrir dois processos com o mesmo arquivo de sessão, usar `resume --last`, clonar o transcript, invocar um fork ou transformar stdout em um pseudo-chat. Essas estratégias violam a identidade/ownership do requisito.

## 8.3 Bridge semântico, arbitragem e uma única fonte de verdade

Entrada humana na TUI precisa ser atribuída à sessão e reconhecida como prompt/controle pelo adaptador. O broker deve observar ou mediar as mutações com a mesma serialização do runtime. Bytes de teclas sozinhos não provam uma mensagem enviada, uma aprovação ou o turno que foi atingido. Não usar scraping visual/OCR como fonte de admissão/recibo.

Um frontend nativo que se conecta por API deve passar por gateway estreito de métodos, campos e escopo. Ele não recebe autorização de engine global nem pode criar/forkar thread sem ação canônica explícita. Ler todas as threads do host não é permitido só porque o token é loopback.

Para TUI em PTY, são necessárias extensão/SDK/hooks/protocolo com eventos/entrada semânticos e autoridade qualificáveis. Terminal keystrokes destinados ao humano podem atravessar o PTY, mas comandos produtivos não podem contornar admissão/auditoria. Se o renderer permite mutações que o bridge não consegue restringir/registrar, manter essa combinação não qualificada, registrar a lacuna e implementar uma ponte adequada antes de anunciar suporte gerenciado.

No máximo um escritor de terminal bruto por sessão; múltiplos leitores autorizados são possíveis. UI pode continuar enviando via coordenador enquanto o terminal está anexado SOMENTE quando ambas as entradas atravessam o mesmo árbitro semântico. Senão a UI continua em leitura/fila com motivo, e disponibiliza retomada de controle num ponto seguro; essa limitação deve ser explicitada e testada, não ocultada sob “suporta simultâneo”.

A regra “Enviar normalmente aguarda o próximo turno” é obrigatória no composer web e no composer Nexus oferecido pelo CLI. A TUI nativa conserva as distinções comprovadas de seus controles (por exemplo, enviar, enfileirar e steer), sem reinterpretar uma tecla silenciosamente. Cada ação produtiva nativa continua passando pelo árbitro e auditada com seu modo efetivo. Se Enter na TUI tiver significado diferente, informar no banner/ajuda; não afirmar que o gesto é idêntico à UI do Nexus. Não passar o mesmo texto por dois canais nem traduzir um pedido normal feito no Nexus em steer porque a TUI prefere esse comportamento.

Takeover de terminal exige escolha humana, revoga o escritor anterior com epoch e atualiza as superfícies; não interrompe o modelo. Expiração da lease de apresentação desanexa o escritor, não fecha a execução. Locks de perfil CLI não podem bloquear todas as outras observações/controles durante horas de attach; reduzir sua duração sem perder proteção de checkpoint.

## 8.4 Detach, sinais e sobrevivência

Fechamento da janela, EOF do transporte de attach, SIGHUP/TERM/KILL do cliente de apresentação, desconexão de rede e encerramento do navegador não são propagados como kill/EOF ao worker. O host mantém os canais necessários à engine, drena saída sem viewers e aplica backpressure limitado por subscriber, evitando que um terminal lento pare o harness.

Oferecer escape externo documentado de detach, por exemplo Ctrl+] quando não houver conflito, validado por plataforma. Não afirmar que Ctrl+C sempre desanexa: em algumas TUIs ele é um comando nativo de interrupção. Separar sinal de fim do cliente de uma tecla/control nativo explicitamente enviada. `okto-nexus work` preserva Ctrl+C como saída do observador. A UI é o controle explícito de interrupção universal do Nexus.

Comando nativo `/exit`, `/quit` ou `/stop` pode ter significado diferente por modo/versão. O catálogo e o banner devem explicar; o wrapper não pode vender encerramento como detach. Para nossa ação Desanexar, nunca encaminhar um comando nativo de close. Pedidos explícitos de close continuam autorizados e com tratamento de fila pendente.

Windows: qualificar encerramento de janela/processo cliente, Job Objects/ConPTY, stdin e console-control. POSIX: controlar grupo/sessão de processos e master PTY; fechamento do slave do viewer não derruba o master. Reutilizar containment atual, não bypass. Acessar o daemon via serviço de usuário é diferente de prometer sobrevivência a logout, reboot ou kill do próprio host.

A garantia é: **fechar o terminal cliente não interrompe trabalho enquanto host/serviço e autorizações vigentes permitem continuar**. Queda de máquina, revogação, expiração de lease produtiva ou shutdown deliberado seguem os contratos de segurança; não manter execução sem autoridade para simular sobrevivência absoluta.

## 8.5 Transferência e contexto salvo

Mapeamento persistido: Server/executor/binding/workspace/agent/runtime-session + adapter/version/fingerprint + native-session/thread ID + driver-generation + branch/context epoch. Paths nativos são privados do host. Labels não resolvem identidade. Guardar correlação no journal/recibo antes de expor sucesso.

Uma transferência preparada mantém a engine antiga como autoridade até commit de troca. Crash entre fases retorna TRANSFER_UNKNOWN com reconciliação; não subir dois owners. Novo writer só é liberado quando o velho perdeu capacidade de efeitos e a continuidade foi validada. Ferramentas, aprovações, uploads, subagentes e filas nativas são parte dessa validação: presença de arquivo de sessão não comprova que todos sobreviveram.

Se for necessário encerrar processo num ponto idle para resume salvo, nenhuma tarefa ativa pode ser abortada como efeito do attach. Se houver trabalho em background que não migra, aguardar ou declarar a limitação. Nunca reaplicar automaticamente uma ferramenta que talvez já tenha executado.

---

# 9. Plano específico por harness — não presumir paridade

## 9.1 Codex

Baseline Core usa `codex_app_server`, JSON-RPC stdio e targeting nativo. A documentação atual oferece caminhos de frontend remoto de TUI para app-server, mas descreve aspectos experimentais e específicos da versão. Isso é um caminho candidato, não suporte pronto do Nexus. [S10, W01–W02]

Prioridade: qualificar transporte de frontend nativo com o MESMO thread e engine gerenciada. Se a versão pinada só permite stdio, uma ponte/gateway compatível pode ser necessária; não mudar para um app-server externo não governado. Validar schema extraído da instalação, initialize/capabilities, seleção de thread, eventos e isolamento. Não permitir que o cliente abra um thread novo por default quando deveria anexar ao selecionado.

Steer usa expectedTurnId real; queue default continua fora desse método. Interrupção por UI preserva target e pausa de fila. Documentar comandos TUI que não possuem equivalência no app-server ou cuja API é experimental. Upgrade de CLI não pode acontecer automaticamente no Connect.

## 9.2 Pi

Baseline Core possui um processo RPC por sessão, eventos estruturados e steer de fronteira. Docs primárias diferenciam prompt, follow-up, steer, abort, estado e sessão; SDK expõe agente/sessão e persistência. [S11, W04–W06]

Prioridade: bridge versionado usando APIs/extension SDK de Pi com um único `AgentSession` e renderer nativo qualificado hospedados no executor, ou um frontend nativo que comprovadamente se conecte ao owner existente. Não presumir que `pi --resume` anexa ao processo RPC. Um wrapper SDK/extension pode exigir build/harness package próprio e nova qualificação; deve preservar ferramentas, skills, extensões, autenticação e configuração revisadas.

Não enviar o mesmo input pelo RPC prompt e também por follow_up; não usar agent_end como sinal suficiente de queue drain quando agent_settled for necessário. `session.dispose()`/fechar stdin não é detach. A bridge precisa separar encerramento da UI e da engine. [W04–W06]

## 9.3 Claude Code

Baseline Core usa stream-json e steer composto por interrupt/reenvio. Docs atuais oferecem background/attach em determinadas versões, mas isso não prova compatibilidade com um processo `-p --input-format stream-json` já gerenciado. [S12, W03, W07]

Prioridade: qualificar attach da superfície nativa ao owner/protocolo apropriado; ou transferência segura para backend nativo hospedado, se necessário. Não usar `--fork-session`, teleport/cloud ou cópia de transcript como preservação da mesma execução. Não apoiar produto em substrate não documentado sem isolamento e qualificação explícitos.

Em nenhuma hipótese abrir `claude --resume <id>` ao lado do stream-json ainda escrevendo a mesma sessão. Interromper/reorientar durante a janela pré-geração segue a recusa do adaptador; não fazer retry por sleep até “dar certo”. Entradas de usuário estruturadas e perguntas/permission requests permanecem distintos.

## 9.4 Gate por capacidade e versão

Cada linha da matriz tem adapter, versão exata, OS, runtime build, modo de sessão, envio nativo, fila, steer/timing, interrupt, comandos, attach vivo, resume salvo, detach com execução, local/remoto e evidência. Estados: observed_in_code, designed, implemented, qualified, unsupported, blocked. “Existe na documentação upstream” não equivale a qualified.

Codex, Pi e Claude são escopo-alvo obrigatório, com entrega por harness possível. Não encerrar a feature inteira marcando todos os attaches como unsupported. Se uma combinação ainda estiver bloqueada, registrar exatamente método/transporte/condição ausente, protótipo testado e próximo passo; implementar as frentes independentes e declarar a entrega parcial corretamente. Ausência de uma ponte upstream pronta é trabalho de integração, não permissão para falsificar a funcionalidade.

---

# 10. Contratos de API e dados propostos

Os nomes abaixo são propostas de fachada. Reutilizar equivalentes já existentes; não montar outro runtime paralelo.

```text
GET  /api/v1/runtime-management/sessions/{session}/interaction
GET  /api/v1/runtime-management/sessions/{session}/conversation?cursor=...
GET  /api/v1/runtime-management/sessions/{session}/inputs?cursor=...
POST /api/v1/runtime-management/sessions/{session}/inputs
POST /api/v1/runtime-management/sessions/{session}/inputs/{input}/cancel
POST /api/v1/runtime-management/sessions/{session}/inputs/{input}/steer
POST /api/v1/runtime-management/sessions/{session}/queue/pause
POST /api/v1/runtime-management/sessions/{session}/queue/resume
GET  /api/v1/runtime-management/sessions/{session}/commands
POST /api/v1/runtime-management/sessions/{session}/commands:execute
POST /api/v1/runtime-management/sessions/{session}/attachments:prepare
POST /api/v1/runtime-management/attachments/{attachment}/detach
```

`{session}` sozinho não é namespace suficiente: resolver com executor e escopo canônico obrigatório, seguindo APIs atuais. Nenhum GET cria sessão, reserva de turno, attach ou grant. Payloads/cursors têm geração, escopo, limites e autorização atual. O stream atual de eventos pode transportar invalidações; bytes do terminal não entram no SSE da Home.

Input conceitual:

```json
{
  "client_intent_id": "ui_<uuid>",
  "scope": {
    "server_id": "S", "executor_id": "E", "binding_id": "B",
    "workspace_id": "W", "workspace_binding_id": "WB",
    "agent_id": "A", "session_id": "SS"
  },
  "expected_session_generation": "G",
  "mode": "next_turn",
  "content": [{"type": "text", "text": "Revise os testes após concluir a alteração atual."}],
  "capability_revision": "CR"
}
```

Ator e origem confiáveis vêm da autenticação/rota, não de `actor_agent_id` enviado livremente pelo cliente. Para steer, acrescentar target-turn/fence exato e revisão do efeito confirmado. Inputs binários seguem upload/artefato existente; o primeiro recorte exige texto e referências autorizadas, não uma nova API de arquivo arbitrário.

Response de aceite: ID estável do input, sequence, queue revision, status, `operation_id` quando resolvido, scope, timestamps, effective delivery timing e `possible_effect`. Idempotência vive no mesmo namespace do autor/Server/sessão/intenção; hash incompatível recusa. Não alegar exactly-once de provedor: garantir não duplicação no Nexus e preservar unknown quando a fronteira externa não comprova o efeito.

Attachment prepare: seleciona exata sessão/estratégia, valida host/permissões, emite capability curta específica a uma única superfície/escritor. Token nunca em URL, argv, logs ou clipboard. Handshake usa canal seguro e challenge; reuso/replay/expiração/revogação testados. Browser recebe apenas instrução segura de CLI quando não existe cliente local autorizado; não lança executável na máquina do usuário por conta própria.

Mensagens do terminal e comandos já originados nativamente entram na auditoria como fatos/intenções correlacionadas, não como outro `messages.send`. Journal canônico/eventos são a fonte do transcript. Novo schema só armazena o que faltar para fila/attachments/mapeamento e deve ter retenção/redação compatíveis.

---

# 11. Autorização, segurança e privacidade

Autenticar leitura, enqueue, dispatch, steer, interrupt, comandos, attach e takeover independentemente. Autorização é revalidada no efeito, não só ao abrir a página. Connector tem identidade de host/execução; isso não lhe concede uma identidade de operador humano. Attach remoto exige prova humana emitida/revalidada pelo Server e capability derivada, sem copiar chave de root do agente.

Revogação limpa conteúdo protegido do browser e fecha o transporte de apresentação; não apagar o histórico canônico nem repetir input. As execuções seguem a política produtiva atual. Inputs ainda não enviados de autor revogado ficam bloqueados ou cancelados pelo contrato explícito, não executados em nome de outro operador.

Origin/TLS/CSRF/websocket auth seguem o contexto atual. Endpoint local não é seguro por definição; limitar usuário OS/ACL, origem, audience e método. Native UI não pode selecionar outro Server/provedor ou `--dangerously-skip-permissions` pelo gateway. Não incluir shell string na API. Entradas são argv/DTO tipados e nomes vêm de allowlists.

PTY/ANSI é conteúdo não confiável: não executar comandos OSC de clipboard, links privilegiados, file:// ou sequências que escapem a sandbox do viewer. TUI no terminal local segue o renderer qualificado; UI web só usa renderer seguro quando necessário e não recebe terminal arbitrário na aba conversa. Arquivos/HTML de ferramenta usam componentes existentes e saneamento.

Tokens de provedor ficam no host aprovado. Paths nativos privados não vazam na listagem global. Texto de prompt armazenado para fila segue retenção/acesso do runtime e não entra em logs de debug ou métricas. Profiling/telemetria local mede latência/contagens, nunca conteúdo.

---

# 12. Atualização, desempenho e integração com a Home

Usar o stream de sessão e snapshots com cursor/epoch. Reconexão consulta snapshot e fecha gaps; eventos duplicados não duplicam bolhas; resposta antiga de uma sessão não é aplicada após trocar para outra. Confirmar coleta de eventos antes de enviar para não perder um término rápido.

Uma consulta em voo por escopo; batching de deltas; não refazer o overview por token. Foco, rascunho, scroll e seleção permanecem estáveis. Se o usuário está lendo mensagens antigas, não autoscroll para o fundo; mostrar “novas mensagens”. Pausa visual não pausa execução nem fila. Ações sempre fazem revalidação própria, inclusive com display pausado.

Home recebe fatos que já entende: Executando, Idle comprovado, pendência, retomada não confirmada, resultado. Fila futura não significa que o turno já começou; terminal desanexado não significa desconectado do Nexus. Uma aprovação pendente continua visível em Needs You. Reorientação composta que interrompe um turno mantém essa história, sem gerar uma entrega de sucesso fictícia.

Metas propostas para qualificação, não medições: aceite de enqueue local p95 <=300 ms sem provedor, abertura de histórico inicial <=2s no dataset/host registrados, nenhuma query por bolha para o histórico inicial, nenhuma conexão stream por mensagem, workers drenando stdout sem viewer lento bloquear. Testar limites de texto/fila, 10 mil mensagens de histórico e múltiplas abas; não serializar todo transcript em overview.

Acessibilidade: teclado, estado por texto, erros junto ao composer, foco previsível, anúncio agrupado do término/pendência sem ler cada token, mobile 360px e zoom 200%. Interrupção, detach, cancelar fila e fechar sessão têm nomes e confirmações distintos. Preserve padrões de idioma existentes; não fazer tradução global neste escopo.

---

# 13. Migrações, versões e rollback

Migrar aditivamente, usando a próxima revisão real do checkout. Não renumerar migrations antigas nem alterar hashes de recibos já emitidos. Registro de inputs/attachments tem versão de contrato e índices por scope/status/sequence; encrypted secret material não pertence a essa fila.

Servidor antigo ou Core/Connector sem capabilities necessárias: novo cliente informa indisponibilidade e preserva fluxo legado; não promete fila durável com cache de browser. Atualização de Core altera wheel/pins/contratos e exige teste conjunto em Server e Connector. Não instalar versão de harness/provedor automaticamente para satisfazer attach.

Para rollback, bloquear novas admissões na superfície nova, reconciliar inputs/controles em trânsito e manter worker/reconciler da fila até resolver ou pausar explicitamente o que já foi aceito. Não desabilitar um worker e abandonar mensagens duráveis silenciosamente. Revogar um vínculo de apresentação afeta somente essa superfície, salvo decisão de runtime independente e autorizada.

Perfis/work/Quick Connect anteriores continuam legíveis. `--no-chat` preservado; mudança de comportamento padrão pós-connect é documentada (pergunta TTY no lugar de entrar automaticamente no prompt Nexus). Scripts continuam não interativos, sem entrada em TUI. Nenhum rollback restaura banco antigo com engines vivas, apaga mensagens ou faz replay para reconstruir o histórico.

---

# 14. Ordem de implementação e gates

| Etapa | Conteúdo | Gate |
|---|---|---|
| SI-00 | Reconciliação, fontes, contratos e provas por harness | G0: modos nativos e limites conhecidos; projeto não presume attach já existente. |
| SI-01 | Modelo/serviço de entrada e fila, correlação, arbitração | G1: próximo turno e controles seguros sem frontend novo. |
| SI-02 | UI de conversa por sessão e catálogo de comandos | G2: ciclo UI completo, sem barramento Operator. |
| SI-03 | Broker de apresentação, mapeamento, ownership e transporte | G3: detach/reattach provados com peers sintéticos e processo real de teste. |
| SI-04 | Integrações nativas Codex/Pi/Claude | G4: capacidades por versão e gaps explícitos, sem prompt falso. |
| SI-05 | CLI connect/attach/resume e local/remoto | G5: escolha inicial e retomada posterior funcionam sem perder contexto. |
| SI-06 | Segurança, falhas, navegador, plataformas e campanhas | G6: execução continua ao fechar terminal, fila consistente e sem efeitos duplicados. |
| SI-07 | Pacote, documentação, rollout e decisão final | G7: requisitos e evidências reconciliados; escopo não comprovado permanece aberto. |

As provas de viabilidade de native attach começam em SI-00, em paralelo à fila; não descobrir incompatibilidade depois de implementar todos os botões. Nenhuma entrega de UI habilita um recurso antes da sua capability estar qualificada. SI-04 pode ser dividida por harness com seus próprios testes; não transformar só a recusa “não suportado” em conclusão do requisito de terminal.


# 15. Backlog executável

Todos os itens são obrigatórios no seu escopo. Reutilizar implementação equivalente com evidência. IDs SI são exclusivos deste plano e não renumeram trabalhos anteriores. A ordem de dependências prevalece sobre tarefas executadas em paralelo. Cada PR inclui testes focais; segurança e correlação não ficam para o final.
## SI-00
### SI-001 — Fixar baseline e compatibilidade dos três componentes

**Estado:** TODO. **Dependências:** nenhuma.  
**Requisitos:** SI-R19, SI-R20, SI-R24.  
**Áreas:** AGENTS.md / CI; pyproject.toml / wheel vendorizado; ledgers existentes.

1. Registrar branch/HEAD/status, versões instaladas e hash dos artefatos Core consumidos.
2. Mapear drift desde os SHAs deste documento sem reset ou substituição de ledgers.
3. Registrar quais módulos e campanhas anteriores continuam aplicáveis e quais precisam de revalidação.

**Aceite:** Baseline reproduzível, sem confundir versão do arquivo/branch/wheel.

**Cenários focais:** SI-T-I05, SI-T-I06.

### SI-002 — Mapear escrita, sessão, fila e autoridade atuais

**Estado:** TODO. **Dependências:** SI-001.  
**Requisitos:** SI-R02, SI-R04, SI-R05, SI-R14, SI-R16, SI-R17.  
**Áreas:** TerminalWork; RuntimeOperations; intents/operations/dispatcher/Core.

1. Traçar UI/CLI→resolve→admit→native write→receipt, incluindo barramento e decisões.
2. Identificar estrutura apta a admissão diferida e cancelamento; não criar segundo scheduler por ausência de investigação.
3. Documentar eventos que provam idle/settled, target/epoch e fronteiras de autorização em cada adapter.

**Aceite:** Mapa fonte/efeito/autor/escopo por caminho, incluindo lacunas exatas.

**Cenários focais:** SI-T-A01, SI-T-A02, SI-T-B21.

### SI-003 — Congelar DTOs, estados e semântica dos controles

**Estado:** TODO. **Dependências:** SI-002.  
**Requisitos:** SI-R04, SI-R05, SI-R06, SI-R07, SI-R08, SI-R10, SI-R14.  
**Áreas:** contracts / ADR; schema HTTP e runtime.

1. Definir scope/input/queue/control/attachment/capability e transições dos capítulos 4–10.
2. Fixar fila após interrupt pausada, promote-to-steer por CAS e tratamento de unknown.
3. Definir gramática -i/--no-interactive, contratos de erros e compatibilidade --no-chat.

**Aceite:** Contrato tipado compartilhado, sem any, com exemplos válidos e negativos.

**Cenários focais:** SI-T-B05, SI-T-C09, SI-T-F08.

### SI-004 — Provar caminhos nativos por harness antes de desenhar attach

**Estado:** TODO. **Dependências:** SI-001, SI-002.  
**Requisitos:** SI-R12, SI-R13, SI-R14, SI-R15, SI-R20, SI-R23.  
**Áreas:** Core adapters; schemas/SDKs upstream versionados; provas isoladas de protocolo.

1. Medir versão/fingerprint das instalações autorizadas e registrar comandos de ajuda/schema somente após consentimento de probe.
2. Prototipar attach vivo ou bridge nativo para Codex, Pi e Claude; confirmar seleção exata e saída que não mata engine.
3. Demonstrar controle/auditoria/isolamento; descartar caminhos que duplicam writer, fork, perdem ferramentas ou bypassam grants.
4. Registrar decisão técnica por harness, dependências/release necessárias e blockers precisos; não implementar só botões com promessa.

**Aceite:** Matriz de estratégia e evidência por harness; a etapa não qualifica produto inteiro.

**Cenários focais:** SI-T-G01, SI-T-G11, SI-T-G12, SI-T-G16, SI-T-I06.

### SI-005 — Preparar fixtures e harnesses sintéticos

**Estado:** TODO. **Dependências:** SI-003.  
**Requisitos:** SI-R03, SI-R05, SI-R06, SI-R13, SI-R22, SI-R24.  
**Áreas:** tests de peers nativos; SQLite descartável; TTY clients.

1. Criar peers com busy, settled tardio, tool approval, eco/delta/snapshot, resposta perdida e múltiplas sessões.
2. Criar dados de fila/leases e dois operadores/two hosts para interleavings determinísticos.
3. Proibir credenciais reais por default e separar campanhas pagas.

**Aceite:** Fixtures reprodutíveis não apresentadas como suporte real.

**Cenários focais:** SI-T-B08, SI-T-E01, SI-T-H14.

## SI-01
### SI-006 — Implementar escopo exato e registros duráveis de input

**Estado:** TODO. **Dependências:** SI-003, SI-005.  
**Requisitos:** SI-R02, SI-R04, SI-R05, SI-R14, SI-R16, SI-R22.  
**Áreas:** Server aplicação/ports/SQLite; schema migrations.

1. Estender intents/outbox ou adicionar metadado auxiliar subordinado à execução existente.
2. Persistir input ID/hash/sequence/scope/autor/modo/payload antes do ACK; índices e limites.
3. Não alterar recibos antigos; GET e resolução de viewer não gravam entradas.

**Aceite:** Input durável único com autorização e transcript ainda separado.

**Cenários focais:** SI-T-A01, SI-T-A02, SI-T-A03, SI-T-A04, SI-T-A05, SI-T-B10, SI-T-B14, SI-T-B15, SI-T-A06, SI-T-A07, SI-T-A09, SI-T-A10.

### SI-007 — Implementar FIFO e despacho na fronteira elegível

**Estado:** TODO. **Dependências:** SI-006.  
**Requisitos:** SI-R04, SI-R05, SI-R15, SI-R16.  
**Áreas:** dispatcher da sessão; capacidade/lease atuais.

1. Serializar admission entre barramento, UI e native bridge pela mesma sessão.
2. Despachar um input por turno somente com prova de estado elegível e geração atual.
3. Usar ordem por sequence, TTL/limites explícitos, nenhuma dupla fila nativa.

**Aceite:** Busy não gera turn.submit concorrente; ordem e fronteira verificadas.

**Cenários focais:** SI-T-B01, SI-T-B02, SI-T-B03, SI-T-B04, SI-T-B06, SI-T-B07, SI-T-B08, SI-T-B09, SI-T-B17, SI-T-B18, SI-T-B21, SI-T-B22, SI-T-B11, SI-T-B12.

### SI-008 — Recuperar intenções e operações sem replay

**Estado:** TODO. **Dependências:** SI-006, SI-007.  
**Requisitos:** SI-R05, SI-R16, SI-R22.  
**Áreas:** reconciler de operações; receipts/journal.

1. Persistir tentativa antes da borda externa e usar a mesma operação no recovery.
2. Distinguir recusa pre-write de possível efeito, bloqueando unknown.
3. Revalidar grants em dispatch e preservar restrições de sessão já vinculada a grant expirado.

**Aceite:** Restart e resposta perdida não duplicam prompts ou renovam autoridade.

**Cenários focais:** SI-T-A08, SI-T-B13, SI-T-B14, SI-T-B16, SI-T-H16.

### SI-009 — Implementar cancelamento de fila e limites

**Estado:** TODO. **Dependências:** SI-006, SI-007.  
**Requisitos:** SI-R05, SI-R22.  
**Áreas:** input cancellation; queue state API.

1. Cancelar somente QUEUED/paused antes do envio irreversível por CAS.
2. Retornar conflito se começou dispatch; manter itens posteriores e turno corrente.
3. Aplicar quota/TTL sem truncar/excluir conteúdo aceito silenciosamente.

**Aceite:** Cancelamento e despacho têm único vencedor; nenhum cancel de runtime implícito.

**Cenários focais:** SI-T-B17, SI-T-B18, SI-T-B19, SI-T-B20.

### SI-010 — Implementar steer e promoção de entrada

**Estado:** TODO. **Dependências:** SI-007, SI-008, SI-009.  
**Requisitos:** SI-R06, SI-R15, SI-R20, SI-R22.  
**Áreas:** runtime intents de controle; Core targeting; capabilities.

1. Fixar target/fence, expor timing e semântica real do adapter.
2. Promover mensagem queued por CAS com operação derivada e retirar da elegibilidade FIFO.
3. Preservar recusa se turno mudou; Claude compound e Pi boundary não disfarçados.

**Aceite:** Uma intenção não é entregue duas vezes; controles não mudam de turno por corrida.

**Cenários focais:** SI-T-C01, SI-T-C02, SI-T-C03, SI-T-C04, SI-T-C05, SI-T-C06, SI-T-C07, SI-T-C08, SI-T-C09, SI-T-C10.

### SI-011 — Interromper com barreira e retomar fila explicitamente

**Estado:** TODO. **Dependências:** SI-007, SI-008.  
**Requisitos:** SI-R07, SI-R16, SI-R22.  
**Áreas:** runtime interrupt; queue pause/resume.

1. Instalar barreira antes do interrupt exato e manter fila após parada.
2. Não encaminhar interrupt a T2 quando T1 termina antes da escrita.
3. Retomar fila somente por ação autorizada; pergunta/approval continuam endpoints próprios.

**Aceite:** Interrupt não vira close e não começa novo turno involuntariamente.

**Cenários focais:** SI-T-C11, SI-T-C12, SI-T-C13, SI-T-C14, SI-T-C15, SI-T-C16, SI-T-C17, SI-T-C18, SI-T-C19.

## SI-02
### SI-012 — Normalizar transcript por origem e identidade

**Estado:** TODO. **Dependências:** SI-002, SI-006.  
**Requisitos:** SI-R01, SI-R03, SI-R14, SI-R18.  
**Áreas:** session events/read models; Core normalization quando necessário.

1. Projetar mensagens/ferramentas/controles por IDs nativos e operação, com paginação e lacunas.
2. Tratar deltas/snapshots/eco sem dedup por texto; subagent com origem explícita.
3. Limitar/redigir conteúdo e não expor raciocínio não publicado.

**Aceite:** Histórico verdadeiro, ordenado e limitado.

**Cenários focais:** SI-T-E01, SI-T-E02, SI-T-E03, SI-T-E04, SI-T-E05, SI-T-E06, SI-T-H20.

### SI-013 — Adicionar composer de usuário na sessão existente

**Estado:** TODO. **Dependências:** SI-006, SI-007, SI-012.  
**Requisitos:** SI-R01, SI-R02, SI-R04, SI-R21.  
**Áreas:** HomeSessionInspection / HomeEntryInspection; RuntimeOperations shared façade.

1. Introduzir conversa como aba padrão e enviar pelo novo coordenador canônico.
2. Enter usa next_turn; rascunho por escopo e estado pending/unknown correto.
3. Reutilizar RequestContext/guards e ações atuais sem criar outro menu.

**Aceite:** Pedido entra como user nativo exato, nunca pelo canal Operator.

**Cenários focais:** SI-T-A01, SI-T-A02, SI-T-E07, SI-T-E08, SI-T-E09, SI-T-E10, SI-T-E12, SI-T-A11, SI-T-A12.

### SI-014 — Apresentar fila, steer e interrupt com efeitos claros

**Estado:** TODO. **Dependências:** SI-009, SI-010, SI-011, SI-013.  
**Requisitos:** SI-R04, SI-R05, SI-R06, SI-R07, SI-R21.  
**Áreas:** session composer/queue components.

1. Listar pendências com posição/status/remove; não mostrar como consumidas.
2. Expor steer separado, consentimento de efeito composto e CAS de promoção.
3. Mostrar barreira pós-interrupt e botão de retomar fila separado de close/detach.

**Aceite:** Toda ação tem escopo e efeito compreensíveis sem formulário técnico.

**Cenários focais:** SI-T-B19, SI-T-C01, SI-T-C05, SI-T-C08, SI-T-C14, SI-T-E07.

### SI-015 — Criar catálogo de comandos tipado e versionado

**Estado:** TODO. **Dependências:** SI-003, SI-004.  
**Requisitos:** SI-R08, SI-R09, SI-R16, SI-R20.  
**Áreas:** Core declarations; Server command capabilities.

1. Definir subset inicial e estados por superfície/instalação/versão/política.
2. Modelar handlers confiáveis e argumentos; distinguir ações Nexus de comandos nativos.
3. Desabilitar recursos não qualificados em vez de string-forward.

**Aceite:** Catálogo demonstra origem e disponibilidade real.

**Cenários focais:** SI-T-D01, SI-T-D02, SI-T-D03, SI-T-D04, SI-T-D10, SI-T-D11, SI-T-D12.

### SI-016 — Implementar comandos e aviso de unsupported

**Estado:** TODO. **Dependências:** SI-013, SI-015.  
**Requisitos:** SI-R08, SI-R09, SI-R18, SI-R21.  
**Áreas:** slash picker UI; typed handlers Server/Core.

1. Mostrar busca/efeito/motivo e confirmação necessária.
2. Unknown/native-only preservam texto; literal depende de capability real.
3. Bloquear shell/admin/update/permission-bypass na API nova; revalidar revisão.

**Aceite:** Comando desconhecido não vira prompt ou execução arbitrária.

**Cenários focais:** SI-T-D04, SI-T-D05, SI-T-D06, SI-T-D07, SI-T-D08, SI-T-D09, SI-T-D10, SI-T-D13.

### SI-017 — Estabilizar navegação, stream e acessibilidade

**Estado:** TODO. **Dependências:** SI-012, SI-013, SI-014, SI-016.  
**Requisitos:** SI-R01, SI-R03, SI-R21.  
**Áreas:** Home panel lifecycle; session stream/controller.

1. Snapshot+stream com cursor e generation; não refetch por token.
2. Preservar foco/rascunho/scroll e impor limpeza em revogação.
3. Mobile/zoom/teclado/IME/aria agrupados, uma camada contextual.

**Aceite:** Fluxo utilizável sem mouse e sem perder contexto no refresh.

**Cenários focais:** SI-T-E09, SI-T-E10, SI-T-E11, SI-T-E12, SI-T-E13, SI-T-E14, SI-T-E15, SI-T-E16.

## SI-03
### SI-018 — Persistir mapeamento nativo e fences de ownership

**Estado:** TODO. **Dependências:** SI-003, SI-004, SI-006.  
**Requisitos:** SI-R14, SI-R15, SI-R22.  
**Áreas:** Core journal/session models; Server session mapping.

1. Mapear namespace canônico a native-session/thread/context epoch/version.
2. Distinguir engine, renderer, runtime generation e viewer attachment.
3. Revalidar mapping em attach/resume; não adotar arquivo/PID por semelhança.

**Aceite:** Nunca há dois owners produtivos da mesma sessão.

**Cenários focais:** SI-T-A04, SI-T-A05, SI-T-G01, SI-T-G16, SI-T-G20.

### SI-019 — Implementar broker e capabilities de attach

**Estado:** TODO. **Dependências:** SI-018.  
**Requisitos:** SI-R12, SI-R15, SI-R16, SI-R18.  
**Áreas:** Server attachment service; host local IPC.

1. Emitir credencial curta por sessão/superfície e writer epoch via autenticação humana.
2. Validar handshake/origin/replay e métodos/contexto permitidos.
3. Takeover explícito e múltiplos leitores sem expor engine global.

**Aceite:** Leitura e escrita restritas à sessão e ao usuário autorizado.

**Cenários focais:** SI-T-G06, SI-T-G07, SI-T-G08, SI-T-G10, SI-T-H03, SI-T-H04, SI-T-H05, SI-T-H06.

### SI-020 — Separar processo durável de cliente terminal

**Estado:** TODO. **Dependências:** SI-004, SI-018, SI-019.  
**Requisitos:** SI-R13, SI-R15, SI-R23.  
**Áreas:** Core native process/containment; PTY/ConPTY ou frontend bridge.

1. Manter engine ou PTY master no host durável, nunca no subprocesso foreground do usuário.
2. Drenar saída continuamente com limites e backpressure por viewer.
3. Tratar desconexão/EOF/signals como detach do cliente, sem fechar stdin da engine.

**Aceite:** Teste de processo prova continuidade após morte do cliente.

**Cenários focais:** SI-T-G03, SI-T-G04, SI-T-G05, SI-T-H07, SI-T-H08, SI-T-H09, SI-T-H13, SI-T-H14, SI-T-H17.

### SI-021 — Arbitrar entradas nativas e UI sem bypass

**Estado:** TODO. **Dependências:** SI-007, SI-010, SI-011, SI-019, SI-020.  
**Requisitos:** SI-R02, SI-R05, SI-R15, SI-R16, SI-R18.  
**Áreas:** typed native input gateway; Core bridge/hooks qualificados.

1. Traduzir/observar comandos produtivos da TUI por eventos semânticos autorizados.
2. Aplicar mesmo árbitro de sessão e atribuição de origem; controlar mutações de thread/config.
3. Bloquear combinação de TUI que não permita preservar autoridade/correlação, sem chamar isso de suporte completo.

**Aceite:** UI e nativo não disparam engines paralelas nem escapam de grants.

**Cenários focais:** SI-T-A02, SI-T-B21, SI-T-G09, SI-T-G10, SI-T-D13, SI-T-H19.

### SI-022 — Estender transporte remoto de sessão

**Estado:** TODO. **Dependências:** SI-019, SI-020, SI-021.  
**Requisitos:** SI-R13, SI-R15, SI-R16, SI-R17.  
**Áreas:** Server remote transport; Connector daemon / WSS / local IPC.

1. Reusar conexão outbound autenticada, separando stream terminal de controle/leases.
2. Encaminhar provas humanas limitadas, não reusar agente como operador.
3. Reconectar por cursor/attachment sem replay de input; CWD remoto preservado.

**Aceite:** Remote tem mesma semântica de detach e nenhuma porta nativa ampla pública.

**Cenários focais:** SI-T-H01, SI-T-H02, SI-T-H03, SI-T-H04, SI-T-H12.

### SI-023 — Implementar transferência/resume seguro e recovery

**Estado:** TODO. **Dependências:** SI-018, SI-020, SI-021, SI-022.  
**Requisitos:** SI-R11, SI-R12, SI-R14, SI-R15, SI-R22.  
**Áreas:** driver transition / native resume; queue barriers; receipt recovery.

1. Transferir somente em estado seguro comprovado e sem trabalho background perdido.
2. Persistir fases e fence; crash não permite dois owners ou replay.
3. Resume salvo preserva contexto exato; sucessora runtime exige linhagem/consentimento, sem mover fila.

**Aceite:** Semânticas attach/resume/transfer inequívocas e recuperáveis.

**Cenários focais:** SI-T-G13, SI-T-G14, SI-T-G15, SI-T-G16, SI-T-G20, SI-T-F15.

## SI-04
### SI-024 — Qualificar integração nativa Codex

**Estado:** TODO. **Dependências:** SI-004, SI-019, SI-020, SI-021, SI-023.  
**Requisitos:** SI-R06, SI-R12, SI-R13, SI-R14, SI-R15, SI-R20.  
**Áreas:** Core codex adapter; schema gerado da versão instalada; native TUI gateway.

1. Implementar estratégia aprovada em SI-004 para frontend Codex na engine existente.
2. Fixar thread/turn, filtrar métodos de engine, correlacionar histórico/entrada e teclas de detach.
3. Executar attach busy, fila, steer target, interrupt, detach/reattach e capability downgrade.

**Aceite:** Native Codex verdadeiro com sessão exata e sem tokens/threads fora do escopo.

**Cenários focais:** SI-T-C02, SI-T-C03, SI-T-G01, SI-T-G05, SI-T-G10, SI-T-G19, SI-T-H05, SI-T-I06.

### SI-025 — Qualificar integração nativa Pi

**Estado:** TODO. **Dependências:** SI-004, SI-019, SI-020, SI-021, SI-023.  
**Requisitos:** SI-R06, SI-R12, SI-R13, SI-R14, SI-R15, SI-R20.  
**Áreas:** Core Pi adapter; SDK/extension bridge versionado; native renderer.

1. Implementar ponte com um único AgentSession/owner, renderer nativo e protocolo de entrada qualificados.
2. Preservar skills/config/auth e settled; separar dispose de detach.
3. Testar pending UI, follow-up, steer boundary, interrupção, persistência e TUI sem dupla fila.

**Aceite:** Pi nativo e UI observam/controlam uma sessão, sem dois processos escritores.

**Cenários focais:** SI-T-B08, SI-T-B22, SI-T-C04, SI-T-G01, SI-T-G04, SI-T-G18, SI-T-H13.

### SI-026 — Qualificar integração nativa Claude Code

**Estado:** TODO. **Dependências:** SI-004, SI-019, SI-020, SI-021, SI-023.  
**Requisitos:** SI-R06, SI-R12, SI-R13, SI-R14, SI-R15, SI-R20.  
**Áreas:** Core Claude stream/background bridge; native attach qualificado.

1. Implementar rota aprovada sem executar resume concorrente ao stream worker.
2. Preservar decisões, guard requesting e efeito steer interrupt+resend com recibos.
3. Validar que background/attach usado realmente conserva tools/config e não é fork/cloud copy.

**Aceite:** Claude nativo verdadeiro sem aborto provocado pelo detach ou perda de contexto.

**Cenários focais:** SI-T-C05, SI-T-C06, SI-T-C07, SI-T-G01, SI-T-G03, SI-T-G17, SI-T-H10.

### SI-027 — Consolidar capability matrix e controles de versão

**Estado:** TODO. **Dependências:** SI-024, SI-025, SI-026.  
**Requisitos:** SI-R08, SI-R12, SI-R20, SI-R24.  
**Áreas:** runtime inventory/capabilities; matrix evidence; installation fingerprint.

1. Publicar suporte por versão/OS/modo com motivos de unavailable.
2. Manter docs upstream separadas da prova da instalação e fechar diferenças de targeting/timing.
3. Preservar caminhos antigos qualificados; novo wheel/pins só com compatibilidade.

**Aceite:** Sem blanket support; cada promessa do produto tem teste associado.

**Cenários focais:** SI-T-D01, SI-T-D03, SI-T-G12, SI-T-I02, SI-T-I06, SI-T-I09.

## SI-05
### SI-028 — Adicionar flags de superfície ao connect

**Estado:** TODO. **Dependências:** SI-003, SI-019.  
**Requisitos:** SI-R10, SI-R19.  
**Áreas:** connect_arguments.py; connect.py; Quick Connect dispatcher.

1. -i/--interactive e --no-interactive mutuamente exclusivos com --no-chat.
2. Plan não anexa; JSON/nonTTY não pergunta; -ni inválido com orientação.
3. Preservar CWD/Git/ID do Harness e hash/receipts anteriores.

**Aceite:** Erros de gramática não produzem efeitos e flags antigas continuam válidas.

**Cenários focais:** SI-T-F04, SI-T-F05, SI-T-F06, SI-T-F07, SI-T-F08, SI-T-F09, SI-T-F10, SI-T-F17.

### SI-029 — Perguntar e abrir nativo após recibo positivo

**Estado:** TODO. **Dependências:** SI-027, SI-028.  
**Requisitos:** SI-R10, SI-R12, SI-R19.  
**Áreas:** post-connect presentation; CLI output.

1. Sem flag TTY, perguntar ao final com default Não; -i pede nativo, não work chat.
2. Separar setup_success de post_action_failure e abertura de sessão adicional autorizada.
3. Retornar ID/escopo/comando de attach antes da TUI, sem tokens.

**Aceite:** Escolha inicial é simples e não altera configuração/autoridade existente.

**Cenários focais:** SI-T-F01, SI-T-F02, SI-T-F03, SI-T-F13, SI-T-F16.

### SI-030 — Implementar session list/attach/resume

**Estado:** TODO. **Dependências:** SI-023, SI-027, SI-028.  
**Requisitos:** SI-R11, SI-R12, SI-R14, SI-R19.  
**Áreas:** CLI main/session commands; catalog/session exact resolver.

1. Listar sessão por conexão/projeto autorizado, com completude e estado.
2. Attach vivo usa mesmo worker, multiple exige escolha, resume salvo usa ID exato e explica efeito.
3. Preservar work resume como receipt recovery; sem --last ou criação invisível.

**Aceite:** Sessão pode ser aberta posteriormente independente da escolha inicial.

**Cenários focais:** SI-T-F11, SI-T-F12, SI-T-F14, SI-T-F15, SI-T-G01, SI-T-G02, SI-T-G16.

### SI-031 — Integrar CLI remoto e Connector

**Estado:** TODO. **Dependências:** SI-022, SI-029, SI-030.  
**Requisitos:** SI-R10, SI-R11, SI-R17, SI-R19.  
**Áreas:** Connector connect/daemon client; Server operator remote access.

1. Oferecer mesma decisão abrir/não abrir no host quando suportada, respeitando gramática própria.
2. No cliente remoto, preparar attach por autoridade humana e host correto; não iniciar substituto local.
3. Usar capacidades/versionamento negociados com diagnóstico de incompatibilidade.

**Aceite:** Local/remoto preservam significado sem importar tokens de root ou paths errados.

**Cenários focais:** SI-T-H01, SI-T-H02, SI-T-H03, SI-T-H12, SI-T-I02.

### SI-032 — Definir sinais, saída de terminal e banner

**Estado:** TODO. **Dependências:** SI-020, SI-024, SI-025, SI-026, SI-030.  
**Requisitos:** SI-R13, SI-R19, SI-R23.  
**Áreas:** TTY launcher; platform lifecycle; help/terminal banner.

1. Documentar detach externo e diferenças reais de Ctrl+C/Esc//exit.
2. Fechar janela/EOF/kill cliente não propaga close/kill ao worker.
3. Restaurar modo do terminal ao sair e não deixar stdin/raw mode quebrado.

**Aceite:** Humano consegue desanexar sem parar; interrupção explícita continua reconhecível.

**Cenários focais:** SI-T-G03, SI-T-G04, SI-T-G05, SI-T-H07, SI-T-H08, SI-T-H09, SI-T-H10, SI-T-H11.

### SI-033 — Preservar Home, comandos e perfis existentes

**Estado:** TODO. **Dependências:** SI-017, SI-029, SI-030, SI-031, SI-032.  
**Requisitos:** SI-R19, SI-R21.  
**Áreas:** Home state projection; Quick Connect; work/participant/legacy.

1. Projetar fila/terminal sem tratar detach como offline ou queued como execução.
2. Executar regressão de profiles, --no-chat, Operator messages/handoffs e participant.
3. Não criar novo menu ou fallback nativo fictício para modo sem suporte.

**Aceite:** Nova interação é adicional e o ciclo antigo não perde capacidades.

**Cenários focais:** SI-T-I01, SI-T-I04, SI-T-F09, SI-T-F14, SI-T-F17.

## SI-06
### SI-034 — Auditar segurança e revogação ponta a ponta

**Estado:** TODO. **Dependências:** SI-021, SI-022, SI-027, SI-031, SI-033.  
**Requisitos:** SI-R15, SI-R16, SI-R17, SI-R18.  
**Áreas:** API/gateway IPC/WSS; scoped capabilities; UI sanitize.

1. Testar replay/token scope/CSRF/Origin/ACL e métodos fora da sessão.
2. Revogar acesso com UI/terminal/fila ativos e provar isolamento de autor.
3. Redigir transcripts/logs e impedir exec/clipboard privilegiados pelo conteúdo.

**Aceite:** Nenhum native bridge vira caminho de bypass ou vazamento.

**Cenários focais:** SI-T-A03, SI-T-H04, SI-T-H05, SI-T-H06, SI-T-H15, SI-T-H16, SI-T-H19, SI-T-H20.

### SI-035 — Executar races e falhas de distribuição

**Estado:** TODO. **Dependências:** SI-008, SI-010, SI-011, SI-023, SI-033.  
**Requisitos:** SI-R05, SI-R06, SI-R07, SI-R15, SI-R22.  
**Áreas:** SQLite transaction tests; Core fault injection; network faults.

1. Forçar interrupção nas fronteiras enqueue/write/ACK/transfer/lease.
2. Provar cancel/promote/dispatch winner, queue pause e recuperação de unknown.
3. Testar owner restart e dois clientes sem duplicate effects.

**Aceite:** Resultados adversariais registrados por intenção e efeito real.

**Cenários focais:** SI-T-B13, SI-T-B16, SI-T-B19, SI-T-C09, SI-T-C13, SI-T-G15, SI-T-H12.

### SI-036 — Qualificar navegador e experiência do usuário

**Estado:** TODO. **Dependências:** SI-017, SI-027, SI-033.  
**Requisitos:** SI-R01, SI-R03, SI-R08, SI-R09, SI-R21.  
**Áreas:** browser real; accessibility; UX acceptance.

1. Executar conversa/queue/steer/approval com dados reais de teste via APIs.
2. Validar viewport, teclado, foco, rascunho, atualização e seleção exata.
3. Inspecionar mensagens humanas de timing/unsupported e obter aceite do fluxo.

**Aceite:** Não substituir e2e por testes de strings/SSR.

**Cenários focais:** SI-T-E09, SI-T-E10, SI-T-E11, SI-T-E12, SI-T-E13, SI-T-E14, SI-T-E15, SI-T-E16, SI-T-D04.

### SI-037 — Qualificar processos e plataformas

**Estado:** TODO. **Dependências:** SI-027, SI-031, SI-032, SI-035.  
**Requisitos:** SI-R13, SI-R17, SI-R23.  
**Áreas:** Windows/macOS/Linux targets; package process tests; transport load.

1. Executar close janela, signal/kill cliente, rede, stdout sem viewer e viewer lento.
2. Medir limites/buffers/latências e restaurar terminal.
3. Registrar OS/versão/backend realmente usado, sem generalizar outra plataforma.

**Aceite:** Detach comprovado por continuidade da execução e resultado, não só PID vivo.

**Cenários focais:** SI-T-H07, SI-T-H08, SI-T-H09, SI-T-H11, SI-T-H13, SI-T-H14, SI-T-H18.

### SI-038 — Executar campanhas reais consentidas

**Estado:** TODO. **Dependências:** SI-034, SI-035, SI-036, SI-037.  
**Requisitos:** SI-R12, SI-R13, SI-R20, SI-R24.  
**Áreas:** Codex/Pi/Claude instalados; workspaces descartáveis; custo autorizado.

1. Rodar UI→native→detach→UI com pedido/resultado e ID estável.
2. Rodar native→UI queue/steer/interrupt; remoto quando anunciado.
3. Associar evidência por harness/OS/versão e manter não executados como NOT_RUN/BLOCKED.

**Aceite:** Nenhuma simulação promovida a suporte real.

**Cenários focais:** SI-T-I07, SI-T-I08, SI-T-I09, SI-T-G11.

## SI-07
### SI-039 — Empacotar e validar compatibilidade de contratos

**Estado:** TODO. **Dependências:** SI-033, SI-034, SI-035, SI-036, SI-037.  
**Requisitos:** SI-R19, SI-R20, SI-R24.  
**Áreas:** Core/Server/Connector artifacts; migrations; golden receipts.

1. Gerar wheels compatíveis e contratos publicados, atualizar pins quando necessário.
2. Instalar em ambiente isolado e testar defaults/upgrade de banco/clients antigos.
3. Preservar hashes/recibos anteriores e reportar exatamente o build validado.

**Aceite:** Pacote não depende de dev server ou fork não fixado.

**Cenários focais:** SI-T-I01, SI-T-I02, SI-T-I05, SI-T-I06.

### SI-040 — Documentar comandos e capacidade efetiva

**Estado:** TODO. **Dependências:** SI-027, SI-029, SI-030, SI-031, SI-032, SI-036.  
**Requisitos:** SI-R08, SI-R10, SI-R11, SI-R13, SI-R19, SI-R20, SI-R24.  
**Áreas:** docs terminal-work/connect; help; support matrix.

1. Documentar diferença entre native user e Operator bus, fila e steer, attach/resume/recover/detach/close.
2. Incluir comandos reais de flags/sessão, limitações por versão/OS e instrução de recuperação.
3. Não prometer native chat com JSON nem comandos globais que não foram qualificados.

**Aceite:** Documentação corresponde ao binário/contratos e mensagens da UI.

**Cenários focais:** SI-T-F01, SI-T-F03, SI-T-F04, SI-T-F14, SI-T-H10, SI-T-I09.

### SI-041 — Decidir gates e executar rollback controlado

**Estado:** TODO. **Dependências:** SI-038, SI-039, SI-040.  
**Requisitos:** SI-R05, SI-R13, SI-R22, SI-R24.  
**Áreas:** release report; feature controls; ledger.

1. Demonstrar rollback sem abandonar fila nem interromper engine inadvertidamente.
2. Conferir todas as tarefas/cenários, blockers e matriz por harness.
3. Separar implemented/qualified/blocked; não publicar release ou campanha adicional sem autorização.

**Aceite:** Relatório final explícito, feature não declarada completa com native goals não implementados.

**Cenários focais:** SI-T-I03, SI-T-I07, SI-T-I08, SI-T-I09.


# 16. Matriz de testes e aceite

Todos os cenários são requisitos, com estado inicial NOT_RUN. PASS exige comando, commit, ambiente, saída e evidência recuperáveis. Nível de teste não é intercambiável: fixture/peer sintético não qualifica TUI nativa, sistema operacional ou provedor. Use barreiras determinísticas e relógios controlados nas corridas, sem sleeps como prova.
## Escopo, papel nativo e admissão

### SI-T-A01 — Entrada não usa barramento
**Dado:** sessão exata autorizada. **Quando:** enviar texto pelo composer. **Então:** uma intenção runtime/entrada, zero message_send, inbox ou handoff implícitos.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A02 — Papel nativo user
**Dado:** input humano aceito. **Quando:** adapter serializa conteúdo. **Então:** papel user no protocolo, sem wrapper Operator no texto, auditoria humana preservada.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A03 — Autor não personificado
**Dado:** cliente tenta forjar actor_agent_id. **Quando:** admitir input. **Então:** usar identidade autenticada ou recusar; nunca ampliar autoridade.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A04 — Tupla divergente
**Dado:** session_id correto em executor ou binding errado. **Quando:** abrir/enviar. **Então:** recusar antes de escrita e não buscar outra sessão.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A05 — Geração antiga
**Dado:** painel mantém geração G1 e sessão está G2. **Quando:** enviar. **Então:** exigir revalidação, sem aplicar entrada automaticamente ao novo contexto.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A06 — Projeto homônimo
**Dado:** mesmo ID do Harness em dois workspaces. **Quando:** selecionar e enviar. **Então:** somente workspace confirmado recebe a entrada.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A07 — GET puro
**Dado:** estado/transcript/capabilities consultados. **Quando:** repetir leituras. **Então:** nenhum grant, sessão, turno, fila, decisão ou attach criados.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A08 — Autorização expira entre passos
**Dado:** enqueue autorizado e grant expira antes do dispatch. **Quando:** worker revalida. **Então:** input bloqueado sem renovação ou transferência de sessão automática.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A09 — Sessão encerrada
**Dado:** conversa existe mas runtime não está apto. **Quando:** enviar. **Então:** recusar ou bloquear de forma explícita, sem new_session implícito.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A10 — Entrada vazia/grande
**Dado:** texto vazio ou além do limite efetivo. **Quando:** enviar. **Então:** validação sem truncamento e sem efeito nativo.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A11 — Entrada aceitação distinta
**Dado:** protocolo aceita mas turno ainda não iniciou. **Quando:** renderizar. **Então:** mostrar aceite/espera, não conclusão ou saída do modelo.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

### SI-T-A12 — Múltiplas sessões
**Dado:** duas candidatas autorizadas na mesma conexão. **Quando:** abrir composer. **Então:** requer seleção exata; recência não decide.  
**Nível:** Unidade + HTTP + peer de protocolo. **Estado:** NOT_RUN.

## Fila e fronteira do turno

### SI-T-B01 — Idle sem fila
**Dado:** sessão apta, idle confirmado. **Quando:** enviar A. **Então:** uma submissão canônica imediata, sem steer.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B02 — Busy enfileira
**Dado:** turno T executando. **Quando:** enviar A. **Então:** A persistida QUEUED, nenhum segundo turno enquanto T não estabiliza.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B03 — FIFO
**Dado:** A B C aceitas durante T. **Quando:** T termina e turnos seguintes estabilizam. **Então:** entregar A depois B depois C, um por turno.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B04 — Sem batching oculto
**Dado:** A e B separadas. **Quando:** liberar próximo turno. **Então:** não concatenar prompts ou modificar conteúdo.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B05 — Dois autores simultâneos
**Dado:** duas abas autenticadas na mesma sessão. **Quando:** enqueue concorrente. **Então:** sequência do Server única e consultável.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B06 — Tool ainda ativo
**Dado:** texto termina mas ferramenta continua. **Quando:** receber evento parcial de término. **Então:** não liberar próxima entrada.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B07 — Pergunta bloqueante
**Dado:** sessão espera aprovação nativa. **Quando:** enviar texto comum. **Então:** texto na fila, não responde aprovação nem desbloqueia por si.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B08 — Pi settled
**Dado:** agent_end chega antes de retry/compaction/agent_settled. **Quando:** processar eventos. **Então:** aguardar fronteira qualificada, sem turno sobreposto.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B09 — Silêncio não idle
**Dado:** nenhum token há um intervalo. **Quando:** varrer fila. **Então:** nenhuma inferência de idle baseada em timeout.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B10 — Persistência antes de ACK
**Dado:** escrita durável da fila falha. **Quando:** enviar. **Então:** recusa, sem mensagem apenas em memória ou ACK otimista.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B11 — Browser fechado
**Dado:** A foi aceita na fila. **Quando:** encerrar aba. **Então:** dispatcher entrega A na hora apropriada sem cliente.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B12 — Terminal fechado
**Dado:** A foi aceita na fila. **Quando:** matar cliente attach. **Então:** execução corrente e fila continuam sem pausa implícita.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B13 — Restart Server
**Dado:** A queued e B talvez enviado. **Quando:** reiniciar serviço autorizado. **Então:** reconciliar B antes de novas submissões; A continua recuperável.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B14 — Resposta enqueue perdida
**Dado:** A commitada mas HTTP caiu. **Quando:** repetir client_intent_id. **Então:** devolver o mesmo item e sequence.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B15 — ID com texto alterado
**Dado:** intenção A retida. **Quando:** repetir ID com B. **Então:** conflito sem sobrescrever payload.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B16 — Dispatch unknown
**Dado:** escrita pode ter chegado sem ACK. **Quando:** restart/reconnect. **Então:** DELIVERY_UNKNOWN e recuperação, sem reenviar cegamente.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B17 — Limite de fila
**Dado:** limite atingido. **Quando:** enviar mais um item. **Então:** recusar somente o novo, preservar os aceitos.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B18 — TTL
**Dado:** input não enviado ultrapassa prazo. **Quando:** avaliar fila. **Então:** EXPIRED visível, não envio tardio nem remoção silenciosa.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B19 — Cancelar versus enviar
**Dado:** worker e cancel disputam o mesmo item. **Quando:** coordenar interleaving. **Então:** só um vencedor; CANCELLED não foi enviado, enviado não é removido falsamente.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B20 — Cancelamento isolado
**Dado:** A queued atrás de turno T. **Quando:** cancelar A. **Então:** T continua, B posterior conserva ordem e não é cancelada.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B21 — Coordenação concorrente
**Dado:** turno de agente e entrada humana disputam sessão. **Quando:** admitir. **Então:** mesmo árbitro evita simultaneidade; política documentada não perde trabalho.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

### SI-T-B22 — Sem double queue
**Dado:** adapter possui follow_up nativo. **Quando:** enviar próximo turno pelo Nexus. **Então:** um único owner de fila e uma única entrega, sem follow_up mais reenvio.  
**Nível:** SQLite + HTTP + dispatcher + fault injection. **Estado:** NOT_RUN.

## Reorientação e interrupção

### SI-T-C01 — Enviar não steer
**Dado:** sessão ocupada com steer disponível. **Quando:** Enter normal. **Então:** QUEUED sem controle nativo de steer.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C02 — Steer Codex exato
**Dado:** turno nativo T conhecido. **Quando:** Reorientar agora. **Então:** enviar expectedTurnId T validado no efeito.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C03 — Steer corrida terminal
**Dado:** T terminou antes do controle. **Quando:** aplicar steer. **Então:** recusar e preservar texto; não atingir T2 nem enviar novo turno.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C04 — Steer Pi fronteira
**Dado:** controle aceito com timing boundary. **Quando:** observar ACK e consumo posterior. **Então:** status separa aceito, pendente de fronteira e aplicado.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C05 — Steer Claude composto
**Dado:** adapter indica interrupt_then_send. **Quando:** abrir ação. **Então:** usuário vê interrupção e confirma efeito; dois estágios correlacionados.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C06 — Claude requesting
**Dado:** turno ainda antes da geração. **Quando:** solicitar steer. **Então:** recusa anterior à escrita preservada; sem retry por sleep nem crash provocado.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C07 — Interrupt seguido de send incerto
**Dado:** Claude interrompeu, novo prompt tem resultado unknown. **Quando:** recuperar. **Então:** não repetir interrupt/prompt; preservar as duas correlações.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C08 — Promover queued
**Dado:** A QUEUED e turno T ativo. **Quando:** escolher reorientar A. **Então:** CAS retira elegibilidade da fila e produz um controle, não duas entregas.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C09 — Promoção versus dispatch
**Dado:** A entrando em DISPATCHING. **Quando:** promover A. **Então:** um vencedor; não virar steer depois de possível envio.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C10 — Steer sem suporte
**Dado:** capability false/unqualified. **Quando:** acionar por API ou UI. **Então:** recusa com motivo; nenhum stop+send substituto.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C11 — Interromper turno selecionado
**Dado:** duas sessões irmãs. **Quando:** interromper sessão 1. **Então:** sessão 2 intacta e runtime 1 não fechado.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C12 — Barreira antes do interrupt
**Dado:** A e B queued e T ativo. **Quando:** pedir interrupt T. **Então:** fila pausada antes da fronteira de próxima admissão.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C13 — Interrupt corrida de término
**Dado:** T completa antes do pedido. **Quando:** processar comando. **Então:** não atingir o próximo turno; barreira e outcome explícitos.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C14 — Fila retida após stop
**Dado:** interrupt confirmado. **Quando:** observar UI e depois fechar painel. **Então:** itens continuam pausados, não excluídos ou retomados por close UI.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C15 — Retomar fila
**Dado:** sessão apta e fila pausada. **Quando:** usuário confirma resume queue. **Então:** revalidar e despachar na ordem restante sem novo grant implícito.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C16 — Interrupt recusado
**Dado:** pedido nativo falha comprovadamente. **Quando:** atualizar painel. **Então:** explicar turno ainda ativo e fila pausada, sem falso sucesso.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C17 — Sim não é aprovação
**Dado:** pergunta de ferramenta pendente. **Quando:** escrever sim no chat. **Então:** mensagem não altera decisão canônica.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C18 — Decisão concorrente
**Dado:** UI e terminal respondem mesmo pedido. **Quando:** aplicar. **Então:** CAS/recibo único; segunda superfície mostra resolvido.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

### SI-T-C19 — Controle não enfileirado como texto
**Dado:** /interrupt ou botão estruturado. **Quando:** confirmar controle. **Então:** chamada de controle tipada, nunca frase para o modelo.  
**Nível:** Unidade + peer nativo + concorrência HTTP. **Estado:** NOT_RUN.

## Catálogo de comandos e literalidade

### SI-T-D01 — Catálogo versionado
**Dado:** instalação e sessão conhecidas. **Quando:** ler commands. **Então:** somente capacidades efetivas com revisão/estado/efeito.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D02 — Comando supported
**Dado:** handler e argumentos válidos. **Quando:** executar. **Então:** endpoint tipado e autorização própria; auditoria na sessão.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D03 — Indisponível no estado
**Dado:** comando exige idle mas sessão busy. **Quando:** selecionar. **Então:** motivo visível e recusa no Server.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D04 — Native only
**Dado:** comando da TUI sem handler web. **Quando:** tentar pela UI. **Então:** aviso nativo somente, sem enviar string como prompt.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D05 — Slash desconhecido
**Dado:** /comando_inexistente. **Quando:** pressionar Enviar. **Então:** aviso, texto preservado e nenhum envio automático.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D06 — Literal comprovado
**Dado:** usuário escolhe enviar slash como texto e adapter suporta escape real. **Quando:** enviar. **Então:** modelo recebe literal, sem skill/template/control expansion.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D07 — Literal não suportado
**Dado:** adapter não comprova escape. **Quando:** selecionar enviar como texto. **Então:** limitação explícita, sem falsa promessa de texto puro.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D08 — Caminho absoluto
**Dado:** texto começa com /tmp/file. **Quando:** classificar. **Então:** não executar como shell/comando conhecido por heurística.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D09 — Comando shell/injeção
**Dado:** argumento contém metacaracteres ou !. **Quando:** executar pela nova API. **Então:** não iniciar shell arbitrário nem aceitar método fora de allowlist.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D10 — Revisão mudou
**Dado:** modelo/settings alterados depois de catálogo. **Quando:** executar comando antigo. **Então:** revalidar capability/argumentos/escopo, sem usar permissão antiga.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D11 — Comando Nexus identificado
**Dado:** status/help locais. **Quando:** renderizar catálogo. **Então:** diferenciar ação Nexus de comando nativo.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D12 — Extensão desconhecida
**Dado:** template/plugin registra comando novo. **Quando:** carregar catálogo. **Então:** não adquirir confiança ou autoridade por nome reportado.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

### SI-T-D13 — Troca de sessão nativa
**Dado:** TUI tenta resume/fork sem suporte bridge. **Quando:** gateway processa. **Então:** negar ou executar transição canônica explícita; fila não migra sozinha.  
**Nível:** Unidade + API + integração UI/adaptador. **Estado:** NOT_RUN.

## Conversa e UI

### SI-T-E01 — Delta e snapshot
**Dado:** mesma resposta tem snapshots e deltas. **Quando:** renderizar. **Então:** sem duplicação/perda de prefixo, usando semântica do adapter.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E02 — Eco da mensagem
**Dado:** submissão local e user echo nativo. **Quando:** correlacionar. **Então:** uma mensagem com referência real, não duas bolhas por texto.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E03 — Texto igual legítimo
**Dado:** dois envios com IDs diferentes e mesmo texto. **Quando:** renderizar. **Então:** ambas mensagens preservadas.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E04 — Histórico incompleto
**Dado:** cursor tem retention gap. **Quando:** abrir conversa. **Então:** lacuna informada sem sintetizar conteúdo.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E05 — Paginação
**Dado:** histórico 10 mil itens. **Quando:** abrir/paginar. **Então:** leitura limitada e cursor estável, sem download integral.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E06 — Subagente
**Dado:** eventos têm origem subordinada. **Quando:** renderizar. **Então:** não atribuir saída a sessão principal indevidamente.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E07 — Mensagem pendente
**Dado:** input QUEUED sem aceite nativo. **Quando:** mostrar. **Então:** status fila, não afirmar modelo já recebeu.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E08 — Falha de rede UI
**Dado:** envio pode ter sido admitido. **Quando:** atualizar/reabrir. **Então:** recuperar mesma intenção antes de habilitar reenviar.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E09 — Foco e rascunho
**Dado:** pessoa digitando e stream atualiza. **Quando:** renderizar. **Então:** texto, foco e alvo preservados.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E10 — Troca de sessão
**Dado:** rascunho em A e usuário abre B. **Quando:** navegar. **Então:** confirmar descarte ou preservar isolado; não mandar texto de A para B.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E11 — Autoscroll
**Dado:** pessoa lê histórico antigo. **Quando:** chegam novos deltas. **Então:** manter posição e informar novas mensagens.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E12 — IME e teclado
**Dado:** composição de caracteres e Shift+Enter. **Quando:** digitar. **Então:** sem envio prematuro; comandos não acionados por Enter comum.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E13 — Mobile e zoom
**Dado:** viewport 360px e zoom 200%. **Quando:** usar fila/controle. **Então:** botões legíveis, foco correto, sem acesso perdido.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E14 — Leitor de tela
**Dado:** saída rápida e fim de turno. **Quando:** anunciar. **Então:** avisos agrupados sem cada token e sem roubar foco.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E15 — Permissão revogada
**Dado:** painel aberto em live. **Quando:** receber 401/403/logout. **Então:** limpar protegido/desabilitar mutações sem apagar journal.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

### SI-T-E16 — Pausa visual
**Dado:** display pausado e engine continua. **Quando:** terminar turno/enviar ação. **Então:** fila continua no Server, decisão revalidada; visual não muda autoridade.  
**Nível:** Componentes + navegador real + API. **Estado:** NOT_RUN.

## CLI e escolha de superfície

### SI-T-F01 — Connect -i
**Dado:** harness suportado, TTY. **Quando:** conectar. **Então:** abrir nativo selecionado após recibo, não prompt work disfarçado.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F02 — Não interativo explícito
**Dado:** --no-interactive. **Quando:** conectar. **Então:** somente conexão, sem TUI, prompt, sessão produtiva ou tarefa extra.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F03 — Pergunta final default
**Dado:** TTY sem flag. **Quando:** concluir connect. **Então:** perguntar abrir harness, default Não; resposta Não retorna ao shell.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F04 — JSON sem flag
**Dado:** --json. **Quando:** conectar. **Então:** zero input/chat, resultado estruturado inclui status e attach argv seguro.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F05 — i com JSON
**Dado:** -i --json. **Quando:** validar argv. **Então:** erro anterior a setup/daemon por esse pedido.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F06 — i sem TTY
**Dado:** stdin ou stdout não terminal. **Quando:** validar -i. **Então:** erro antes dos efeitos, sem abrir console invisível.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F07 — Plan -i
**Dado:** --plan -i em TTY e sem --json. **Quando:** executar. **Então:** só plano; nenhum attach/runtime/provedor adicional.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F08 — Flags conflitantes
**Dado:** -i com --no-interactive ou --no-chat. **Quando:** parse. **Então:** erro determinístico, sem última flag vencer.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F09 — No chat legado
**Dado:** --no-chat existente. **Quando:** conectar. **Então:** sem pós-interface; --profile e JSON preservados.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F10 — ni não abreviação
**Dado:** -ni ou --inter digitados. **Quando:** parse. **Então:** diagnóstico útil, sem composição inesperada.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F11 — Attach exato
**Dado:** --id e --session-id concordantes. **Quando:** abrir. **Então:** mesma sessão, nunca última ou nova por fallback.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F12 — Attach múltiplas
**Dado:** várias sessões e sem ID exato. **Quando:** usar TTY versus script. **Então:** picker no TTY; seleção requerida no script.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F13 — Falha pós-setup
**Dado:** binding criado, nativo indisponível. **Quando:** -i tenta abrir. **Então:** manter conexão e pós-ação falha separada; não repetir setup.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F14 — Work resume preservado
**Dado:** submissão incerta antiga. **Quando:** work resume. **Então:** recuperar recibo, não chamar attach ou resumir latest.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F15 — Resume salvo explícito
**Dado:** processo encerrado com contexto válido. **Quando:** session resume ID. **Então:** explicar cold resume/linhagem; sem fork ou novo contexto silencioso.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F16 — Sem permissão abrir
**Dado:** conexão existe e grants insuficientes. **Quando:** attach exige runtime open. **Então:** informar revisão necessária, não renovar autorização.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

### SI-T-F17 — Quick Connect invariantes
**Dado:** CWD/Git/--id colidem ou personalizam. **Quando:** usar novos flags. **Então:** mesmas regras de nome/root/ID e aprovação sem alterar profile por UI mode.  
**Nível:** Parser + pseudoterminal + pacote instalado. **Estado:** NOT_RUN.

## Attach, ownership e protocolos nativos

### SI-T-G01 — Mesma engine viva
**Dado:** sessão em execução. **Quando:** anexar terminal. **Então:** mesmo native session/thread e trabalho, sem novo processo escritor ou teste.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G02 — Mesmo contexto depois de detach
**Dado:** turno terminou sem cliente. **Quando:** reanexar. **Então:** histórico/ID preservados e sem prompt automático.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G03 — Sem close stdin
**Dado:** Claude stream busy. **Quando:** fechar cliente attach. **Então:** canal da engine mantido e resultado ainda observado.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G04 — Master PTY durável
**Dado:** worker TUI hospedado. **Quando:** viewer fecha slave/transporte. **Então:** master/engine continuam e I/O é drenado.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G05 — Frontend separado
**Dado:** engine hospeda TUI remota. **Quando:** frontend termina. **Então:** engine continua, cleanup só do frontend.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G06 — Um escritor
**Dado:** dois terminais tentam controlar. **Quando:** attach concorrente. **Então:** um writer e outro read-only/recusa explícita.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G07 — Takeover
**Dado:** segundo operador autorizado confirma transferência. **Quando:** trocar writer. **Então:** epoch novo, velho perde efeitos, turno continua.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G08 — Lease de viewer expira
**Dado:** cliente some sem detach. **Quando:** expirar apresentação. **Então:** liberar viewer sem parar engine ou renovar lease produtiva.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G09 — UI e nativo simultâneos
**Dado:** bridge semântico qualificado. **Quando:** enviar ambos. **Então:** arbiter serializa/atribui origens sem duas engines.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G10 — Token de engine amplo proibido
**Dado:** TUI tenta listar/abrir outro thread. **Quando:** gateway recebe. **Então:** negar fora do escopo sem vazamento.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G11 — Native frontend não falso
**Dado:** pedido -i. **Quando:** observar processo/render. **Então:** frontend nativo real; prompt Nexus não satisfaz esse aceite.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G12 — Native indisponível
**Dado:** versão não qualificada. **Quando:** tentar attach. **Então:** limitação explícita e execução atual intacta; tarefa de integração não marcada pronta.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G13 — Transferência espera fronteira
**Dado:** backend precisa transferir e turno busy. **Quando:** solicitar attach. **Então:** aguardar ponto seguro ou recusar; sem abortar ferramenta.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G14 — Transferência com tool background
**Dado:** background não migrável. **Quando:** tentar transferir. **Então:** não matar/reexecutar ferramenta; mostrar limitação.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G15 — Crash durante transferência
**Dado:** depois de fence antes de novo owner. **Quando:** recuperar. **Então:** apenas um owner pode produzir efeito; unknown reconciliado.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G16 — Fork não é resume
**Dado:** adapter só oferece clone/fork. **Quando:** retomar. **Então:** não declarar mesma sessão; ação separada ou bloquear requisito.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G17 — Claude fase unsafe
**Dado:** geração ainda não iniciou. **Quando:** steer via UI/nativo bridge. **Então:** preservar guard e recusa antes da escrita.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G18 — Pi duas filas
**Dado:** bridge SDK e RPC coexistem. **Quando:** enviar queued/steer. **Então:** só uma AgentSession/owner e uma entrega por intenção.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G19 — Codex seleção default
**Dado:** TUI tenta iniciar thread novo ao attach. **Quando:** handshake. **Então:** forçar/revalidar alvo exato ou abortar attach sem criar thread.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

### SI-T-G20 — Native mudança contexto
**Dado:** comando nativo cria nova conversa autorizado. **Quando:** atualizar mapeamento. **Então:** novo contexto explicitado e filas antigas não são reaproveitadas.  
**Nível:** Core + broker + processos reais controlados + campanhas. **Estado:** NOT_RUN.

## Remote, sinais e segurança

### SI-T-H01 — Remoto outbound
**Dado:** Connector em outra máquina. **Quando:** anexar por Server autenticado. **Então:** transporte usa canal aprovado, sem porta pública/SSH improvisado.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H02 — CWD remoto
**Dado:** cliente em /A e host em /B. **Quando:** abrir sessão remota. **Então:** /B preservado, Git/CWD local não substitui root.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H03 — Credencial humana
**Dado:** Connector só tem credencial de agente. **Quando:** tentar gerar attach humano. **Então:** exigir autorização humana/derivada, sem elevação de agente.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H04 — Token replay
**Dado:** capability de attach usada de novo ou em outra sessão. **Quando:** handshake. **Então:** rejeitar reuso/escopo/audience inválidos.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H05 — Segredo em argv
**Dado:** attach requer token. **Quando:** lançar frontend. **Então:** token por canal protegido, ausente de URL, argv, clipboard e logs.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H06 — Origin indevido
**Dado:** browser de origem externa tenta socket. **Quando:** autenticar. **Então:** bloqueio conforme Origin/CSRF e autorização atuais.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H07 — Close terminal POSIX
**Dado:** worker executa tarefa longa autorizada. **Quando:** fechar janela/SIGHUP cliente. **Então:** worker e fila continuam com evidência de PID/resultado.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H08 — Close terminal Windows
**Dado:** cliente/console fecha sob ConPTY/Job. **Quando:** executar caso real. **Então:** sem kill acidental do processo/árvore da engine.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H09 — Cliente KILL
**Dado:** matar somente processo de apresentação. **Quando:** observar host. **Então:** execução segue; lease de viewer expira independentemente.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H10 — Ctrl C nativo
**Dado:** tecla tem semântica de interrupt no harness. **Quando:** usuário a envia. **Então:** documentar/mediar como controle explícito, não prometer detach universal.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H11 — Escape detach
**Dado:** atalho externo documentado. **Quando:** desanexar. **Então:** nenhuma chamada runtime.close/interrupt/EOF worker.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H12 — Rede interrompida
**Dado:** attach remoto perde transporte. **Quando:** reconnect. **Então:** turno segue conforme lease produtiva, sem replay de teclas/prompts.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H13 — Viewer lento
**Dado:** cliente para de consumir saída. **Quando:** produção contínua. **Então:** backpressure local ao viewer, bounded buffers e gap/reattach sem travar engine.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H14 — Saída excessiva
**Dado:** worker produz grande log. **Quando:** sem viewers. **Então:** drenagem/limites e política explícita; não OOM ou bloqueio de pipe.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H15 — ANSI malicioso
**Dado:** evento contém OSC clipboard/link/códigos perigosos. **Quando:** render UI. **Então:** nenhum acesso privilegiado/execução/clipboard automática.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H16 — Autor revogado com queued
**Dado:** usuário perde acesso. **Quando:** worker revalida input. **Então:** não executar sob outro autor nem expandir permissão.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H17 — Detach não é revoke
**Dado:** fechar UI com execução admitida. **Quando:** avaliar políticas. **Então:** não revogar grant por desconexão de apresentação.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H18 — Host shutdown
**Dado:** serviço é parado explicitamente. **Quando:** comparar com detach. **Então:** respeitar lifecycle de shutdown, não prometer continuidade impossível.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H19 — Commands privilege
**Dado:** terminal tenta bypassPermissions/exec arbitrário. **Quando:** gateway processa. **Então:** negar não qualificado ou exigir fluxo de autorização, sem bypass implícito.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

### SI-T-H20 — Paths e segredos
**Dado:** mensagem/tool revela payload protegido. **Quando:** listar transcript global. **Então:** escopo/redação/retention respeitados, sem vazar por resumo ou erro.  
**Nível:** HTTP/WSS + OS nativo + isolamento adversarial. **Estado:** NOT_RUN.

## Compatibilidade, produto e rollout

### SI-T-I01 — Migration aditiva
**Dado:** banco com recibos antigos. **Quando:** migrar. **Então:** hashes antigos preservados e novos campos opcionais.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I02 — Downgrade capability
**Dado:** cliente novo, Core/Connector antigos. **Quando:** abrir recursos novos. **Então:** indisponibilidade explícita sem simular fila/attach local.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I03 — Rollback com fila
**Dado:** mensagens aceitas e em trânsito. **Quando:** desabilitar nova UI. **Então:** reconciler/controle mantidos, nenhuma mensagem abandonada ou replay.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I04 — Home estados
**Dado:** enviar, queued, steer, detach, resultado. **Quando:** observar Active/Needs You/Results. **Então:** fila não vira RUNNING, detach não vira offline, entrega sem verificação fictícia.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I05 — Pacote instalado
**Dado:** wheels/artefatos compatíveis gerados. **Quando:** instalar isolado. **Então:** CLI/UI/Core/Connector usam contratos/pins corretos, sem dev server.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I06 — Versão não igual docs
**Dado:** harness instalado difere de referência. **Quando:** calcular capabilities. **Então:** novo suporte somente com qualificação, não por versão do artigo.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I07 — Jornada UI terminal UI
**Dado:** conectar sem interação, mandar UI, attach, fechar, voltar UI. **Quando:** executar com provedor consentido. **Então:** mesma conversa e continuidade, sem novo processo escritor.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I08 — Jornada terminal fila steer
**Dado:** conectar -i, executar, enfileirar UI, reorientar, detach. **Quando:** executar consentido. **Então:** próximo turno padrão, steer explícito e evidências separadas.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

### SI-T-I09 — Gates por harness/plataforma
**Dado:** só uma campanha rodou. **Quando:** encerrar relatório. **Então:** não marcar outros harnesses/OS PASS nem encerrar requisito faltante como unsupported satisfeito.  
**Nível:** Integração + pacote + campanha. **Estado:** NOT_RUN.

# 17. Evidências, limites de execução e definição de pronto

Antes de rodar comandos, ler scripts reais de testes e dependências do checkout. Usar suites existentes e adicionar os casos deste plano. Não assumir que `npm test` abre navegador. Testes do Core executam peers/protocolos; processos nativos, browser e campanhas reais têm relatórios separados. Nenhuma campanha paga está autorizada por este documento: requer consentimento, teto de gasto e dados descartáveis.

Registrar em `plans/session_interaction/` (ou convenção equivalente): baseline, mapa de fontes, ADR de fila/arbitragem, ADR por integração nativa, contrato HTTP/transport, capability-matrix, ledger, evidências de regressão/faults/OS/browser, desempenho e relatório final. Versão do harness, hash do binário, OS, versão Core e artefato instalado fazem parte de cada campanha. Não publicar tokens, banco real ou prompts privados.

**Gates obrigatórios:**

- UI entrega conteúdo como user nativo da sessão, sem inbox/handoff artificial; a fila sobrevive ao cliente.
- Busy aguarda; steer só por ação específica e com semântica correta do harness.
- UI interrompe o turno exato, pausa pendências e permite retomada explícita.
- Comandos listados refletem capacidade real; desconhecidos/unsupported não são enviados silenciosamente como prompt.
- Connect -i abre nativo; sem flag pergunta; negativo só conecta; scripts nunca perguntam.
- UI e terminal podem ser usados em momentos diferentes sem perder correspondência da sessão. Attach vivo não cria fork nem reenvia pedido.
- Fechar janela, matar cliente ou perder rede não interrompe trabalho nem a fila por causa da apresentação; host/autoridade continuam com seus limites próprios.
- Codex/Pi/Claude têm evidência própria para toda promessa que for habilitada. Uma ponte ainda bloqueada permanece requisito aberto.
- Fluxos antigos, Home, Quick Connect, grants e recibos continuam coerentes.

Não aceitar “pronto” baseado só em botões, subprocesso foreground, `resume --last`, texto de terminal capturado sem correlação, mocks de suporte nativo ou capacidade marcada true no registry. Não retirar invariantes de segurança para passar uma demonstração. Implementação, qualificação sintética, qualificação nativa e aceite de produto são estados diferentes.

A entrega final deve incluir uma demonstração com duas sessões do mesmo agente: uma continua trabalhando enquanto a outra recebe pedido/steer/interrupt. Abrir terminal na primeira, fechar, observar resultado na UI, voltar à mesma sessão e conferir que a irmã permaneceu intacta. Incluir o caso de autorização expirada, desconhecido de entrega, input queued e comando unsupported.

# 18. Prompt de execução

O arquivo `PROMPT_CODEX_NEXUS_SESSOES_INTERATIVAS_R1.md` está pronto para iniciar o trabalho. Use o ledger fornecido como registro inicial desta feature, sem sobrescrever os ledgers existentes de outras frentes. Havendo drift, registrar correspondência de arquivo/contrato e manter requisitos deste plano. Não executar deploy, release ou merge protegido sem autorização.

# 19. Fontes e limites da inspeção

As fontes S01–S13 são snapshots de código/documentação selecionados. Comentários de qualificação são relatos do projeto, não campanhas repetidas nesta elaboração. Fontes W01–W07 são documentação primária consultada em 17/11/2026; podem descrever versões posteriores às instalações/pins locais. Confirmar schema/versão no início da implementação. A consulta não confirma compatibilidade de attach entre qualquer TUI e os adaptadores atuais.

- **[S01] Nexus versão e dependências:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/pyproject.toml
- **[S02] Core versão declarada:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/pyproject.toml
- **[S03] Connector versão e dependências:** https://github.com/OktoLabsAI/okto-nexus-connector/blob/a4d510080d7a685fa442a4c5c30419952589fe04/pyproject.toml
- **[S04] RuntimeOperations e escopo exato:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/frontend/src/components/RuntimeOperations.tsx
- **[S05] HomeEntryInspection e abertura de sessão:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/frontend/src/components/home/HomeEntryInspection.tsx
- **[S06] TerminalWork: submit/resolve/admit/recover:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/src/okto_nexus/application/terminal_work.py
- **[S07] Documentação do trabalho por terminal:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/docs/terminal-work.md
- **[S08] Connect e composição Quick Connect:** https://github.com/OktoLabsAI/okto-nexus/blob/8b4001fa1db17bf29d0c773eed3535e79fce70cb/src/okto_nexus/adapters/inbound/cli/connect.py
- **[S09] Registry Core e targeting/timing:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/src/nexus_connector_core/native/registry.py
- **[S10] Adaptador Codex app-server:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/src/nexus_connector_core/native/adapters/codex.py
- **[S11] Adaptador Pi RPC:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/src/nexus_connector_core/native/adapters/pi.py
- **[S12] Adaptador Claude stream-json:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/src/nexus_connector_core/native/adapters/claude_code_stream.py
- **[S13] Guia de integração Core — referência estrutural, reler versões:** https://github.com/OktoLabsAI/okto-nexus-connector-core/blob/497ee2b7a14b99c50cba97eac74f3b00d4863f26/docs/adding-a-runtime.md
- **[W01] OpenAI — Codex App Server (consulta oficial; redireciona ao portal Learn):** https://developers.openai.com/codex/app-server
- **[W02] OpenAI — Developer commands / remote terminal UI:** https://learn.chatgpt.com/docs/developer-commands
- **[W03] Anthropic — Claude Code CLI reference:** https://code.claude.com/docs/en/cli-reference
- **[W04] Pi — RPC protocol, documentação do projeto:** https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/rpc.md
- **[W05] Pi — RPC commands, semântica de prompt/steer/follow-up:** https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/rpc-commands.md
- **[W06] Pi — SDK e lifecycle da sessão:** https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/sdk.md
- **[W07] Anthropic — Agent view, background/attach/detach:** https://code.claude.com/docs/en/agent-view


Os planos anteriores de Home e Quick Connect foram consultados para preservar decisões de produto (ID do Harness, detach de observador, Home com três colunas). Seus invariantes pertinentes foram explicitados neste documento; o executor não precisa aplicar emendas de um plano anterior para compreender esta feature.

---
**Controle:** SESSION-INTERACTION-R1. Proposta completa inicial de implementação. Nenhuma alteração nos repositórios ou teste da aplicação foi executado durante a preparação deste pacote. Redução de escopo requer decisão explícita registrada; ausência de capacidade deve ser reportada, não escondida sob um fallback.
