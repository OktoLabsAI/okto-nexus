# SAFE-TRACE — ATN e OBS

Base `bcf0e8aa`; plano fixo SHA `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996`. Leitura de implementação/assertions e resultados existentes, sem executar testes ou alterar checkout/ledger.

**Conclusão:** as20 tarefas e40 cenários têm implementação/reuso e prova específica preservada no escopo declarado. Não identifiquei lacuna literal de produto ou assertion/PASS que exija novo teste. Os vínculos detalhados estão em `matrix.json`; nenhum status foi promovido por este agente.

AC-06 pode ser VERIFIED: publish altera somente fatos/eventos observacionais; blocked/idle/completion/seen não concluem trabalho nem liberam a fila. Apenas evento terminal canônico avança o turno. RG03 preserva reserva/TTL, prioridade, FIFO, fairness e elegibilidade. Provedor real é irrelevante para essa proibição.

OB-24 pode ser VERIFIED no contrato Windows canônico: há toggle OBS on→off mantendo Core local, RG01 atual com dois participantes MCP e runtime sob OBS=false, e RG11 remoto atual com Connector/Core reais via HTTP/WSS e MCP. A configuração vem de bootstrap com ambiente vazio/default false; o peer nativo é sintético. Falta ligação no ledger, não foi encontrado comportamento ausente.

ATN01–08, hoje IMPLEMENTED, têm prova de verificação delimitada: catálogo, filtros/contagens, preferências/CAS/passividade, SSE/deadlines, comandos canônicos e browser/semântica acessível. AT/OB já VERIFIED mantêm seu escopo.

## Matriz finita

| ID | Requisito literal | Prova | Recomendação |
|---|---|---|---|
| ATN-01 | **ATN-01 — serviço de projeção.** Compor consultas em lote sobre aprovações, perguntas, handoffs, receipts, recuperação e entregas. Retornar referências, não duplicar payloads secretos. Reutilizar serviços/ports quando disponíveis; evitar N+1 e consultas sem limite. | projection | VERIFIED no escopo declarado |
| ATN-02 | **ATN-02 — armazenamento auxiliar.** Persistir somente seen/snooze e, se indispensável, uma projeção materializada reconstruível com referências de origem. Não criar uma nova fila de handoffs ou aprovações. Modelar a preferência sob o principal de operador já existente; não adicionar usuários/agentes apenas para suportar o painel. Em uma instalação de operador único, documentar esse escopo compartilhado entre dispositivos. | preferences | VERIFIED no escopo declarado |
| ATN-03 | **ATN-03 — transações e leitura.** GET não materializa decisões nem altera lifecycle. Atualizações de projeção devem ocorrer após confirmação do fato original ou em manutenção limitada. Auditoria/autenticação já existente continua separada; não alterar seus contratos sob pretexto de leitura pura. | passive | VERIFIED no escopo declarado |
| ATN-04 | **ATN-04 — API.** Propor `GET /api/v1/attention`, `GET /api/v1/attention/summary` e ações explícitas de visto/adiado. Usar envelope, autenticação de operador e controles de origem do produto. Os nomes podem ser adequados na implementação; seus contratos devem permanecer únicos e versionados. | api | VERIFIED no escopo declarado |
| ATN-05 | **ATN-05 — SSE e reconciliação da visão.** Reutilizar o canal SSE como notificação de invalidação; ler a projeção canônica em resposta. Reunir rajadas, não buscar todos os dados a cada token. Se um fato relevante não gerar evento, acrescentar um evento mínimo após commit ou usar refresh limitado da visão; não criar um monitor por agente. | stream, temporal | VERIFIED no escopo declarado |
| ATN-06 | **ATN-06 — UI integrada.** Adicionar item ao menu e badge global. Preservar Graph, Meta-harness e páginas especializadas. Mostrar agente, contexto, motivo, idade, origem/atualidade e ação principal. Permitir abrir a sessão ou o registro original sem navegar por várias telas. | ui | VERIFIED no escopo declarado |
| ATN-07 | **ATN-07 — interação segura.** Visto não resolve. Adiado não aprova nem suspende a execução. Aprovar mantém confirmação e fencing atuais. Resultado desconhecido oferece inspeção; nunca um botão “repetir tudo”. Ações sobre fatos que mudaram exibem conflito e recarregam a situação. | interaction | VERIFIED no escopo declarado |
| ATN-08 | **ATN-08 — acessibilidade.** Navegação por teclado, foco previsível, textos que não dependem de cor, estados vazios distintos de erro e light/dark conforme o dashboard. A abertura da página não deve mostrar toasts repetidos de todo o histórico. | accessible | VERIFIED no escopo declarado |
| OBS-01 | **OBS-01 — vínculo explícito.** Registrar uma fonte de atividade para uma identidade existente e workspace aprovado. Não associar agente pela igualdade de nome, hostname, diretório ou pane. Exigir seleção explícita e autenticação/consentimento compatível. | registration | VERIFIED no escopo declarado |
| OBS-02 | **OBS-02 — capacidade restrita.** Reutilizar a infraestrutura de credenciais escopadas quando apropriado, sem ampliar os EPTs de leitura existentes. Caso seja necessária uma nova família de token, ela deve ser opaca, revogável, armazenada com proteção/hash apropriado, de curta duração e aceita exclusivamente nos endpoints de telemetria previstos. | audience | VERIFIED no escopo declarado |
| OBS-03 | **OBS-03 — ordenação e replay.** Aceitar sequência monotônica por fonte/instância/generation. Mesma sequência e mesmo hash é idempotente, não emite outro evento nem renova validade. Mesmo número com conteúdo diferente conflita. Sequência antiga não sobrescreve o estado atual. Geração antiga não altera a nova. | replay | VERIFIED no escopo declarado |
| OBS-04 | **OBS-04 — freshness.** Usar horário de recebimento do Server e idade/horário observado com tolerância de relógio documentada. Reporte excessivamente antigo não vira estado atual apenas porque chegou agora. Relógio futuro não cria validade ilimitada. Após reconnect, buscar snapshot novo da fonte e publicar estado atual; não reproduzir backlog como se fosse observação recente. | freshness, limits | VERIFIED no escopo declarado |
| OBS-05 | **OBS-05 — empacotamento opcional.** Implementar um módulo opcional invocado, por exemplo, por `okto-nexus observe herdr`. Ele roda perto da instância Herdr e publica via HTTP autenticado no Nexus. Não exige o daemon Connector, não registra executor e não inicia junto com o Server por padrão. | optional | VERIFIED no escopo declarado |
| OBS-06 | **OBS-06 — contrato real instalado.** Usar a CLI/socket API documentada. Registrar versão e obter o schema da instalação quando suportado (`herdr api schema --json`). A documentação pública não basta para presumir campos da versão instalada. Criar fixtures a partir do contrato compatível, sem dados pessoais. [H01] | herdr_contract | VERIFIED no escopo declarado |
| OBS-07 | **OBS-07 — identidade do ocupante.** Mapear instalação/sessão Herdr + pane + identidade/generation do ocupante para instância observada. Nome é só alias. Fechar, mover, renomear pane ou substituir processo não pode transferir silenciosamente o vínculo ao novo agente. | occupant | VERIFIED no escopo declarado |
| OBS-08 | **OBS-08 — leitura sem controle.** A integração consulta/lista/assina; não chama `agent.start`, `agent.prompt`, `send-keys`, focus, aprovação ou kill. Seu token Nexus também não pode executar essas ações. Um plugin Herdr roda com permissões do usuário: documentar essa fronteira; token restrito no Nexus não é sandbox de código local. [H03] | observer_readonly | VERIFIED no escopo declarado |
| OBS-09 | **OBS-09 — semântica de término.** Usar `completion_seq` ou referência equivalente somente quando disponível e coerente com o schema. Sem prova de nova conclusão, mostrar idle, não produzir uma entrega “concluída”. `agent.wait` do Herdr observa atividade, não a conclusão de um handoff específico; não usá-lo como verificador de tarefas Nexus. [H02] | completion | VERIFIED no escopo declarado |
| OBS-10 | **OBS-10 — exemplo mínimo.** Documentar registro autorizado, obtenção de capacidade, publicação, sequência, TTL, revogação e encerramento. Oferecer helper pequeno, isolado e testado. Não exigir plugin framework ou implementação de `LocalRuntimeCore`. | helper | VERIFIED no escopo declarado |
| OBS-11 | **OBS-11 — projeção.** Acrescentar `external_blocked`, `external_completion_unseen` e `external_observation_stale` à central, com origem, atualidade e limitação explícitas. Fonte externa bloqueada sem pedido canônico não recebe botão “aprovar”; a ação é inspecionar no ambiente de origem. | external, canonical_isolation | VERIFIED no escopo declarado |
| OBS-12 | **OBS-12 — fontes concorrentes.** Para uma mesma instância explicitamente correlacionada, manter precedência/proveniência definida: fatos canônicos do Core não são sobrescritos por inferência de terminal. Divergência pode aparecer como diagnóstico, sem alterar autorização. Fontes sem correlação suficiente permanecem separadas. | correlation | VERIFIED no escopo declarado |
| AT-01 | Aprovação pendente aparece para operador autorizado. | native_authority | VERIFIED no escopo declarado |
| AT-02 | Aprovação expirada perde ação e preserva referência histórica adequada. | native_authority, temporal | VERIFIED no escopo declarado |
| AT-03 | Pergunta destinada ao agente A não vira pergunta respondível pelo operador como A. | native_authority | VERIFIED no escopo declarado |
| AT-04 | CLAIMED normal e inferência sem eventos não geram incidente de travamento. | canonical_states | VERIFIED no escopo declarado |
| AT-05 | VERIFYING automático permanece acompanhamento, sem inventar verificador humano. | canonical_states | VERIFIED no escopo declarado |
| AT-06 | Resultado desconhecido não oferece retry automático. | interaction, canonical_states | VERIFIED no escopo declarado |
| AT-07 | Marcar visto/adiar não altera aprovação, inbox, handoff ou operação. | preferences, passive | VERIFIED no escopo declarado |
| AT-08 | Mesmo episódio resiste a refresh/reconnect; episódio posterior do mesmo objeto volta a aparecer. | preferences, temporal | VERIFIED no escopo declarado |
| AT-09 | Ação com revisão antiga conflita e recarrega o fato; não decide pedido novo. | interaction, native_authority | VERIFIED no escopo declarado |
| AT-10 | Lista, total e filtros respeitam a mesma autorização e paginação. | api | VERIFIED no escopo declarado |
| AT-11 | Falha de leitura mostra dado stale; 403/revogação remove conteúdo protegido. | stream | VERIFIED no escopo declarado |
| AT-12 | SSE perdido/gap resulta em resnapshot, sem sumir com pendências ou duplicar toasts. | stream | VERIFIED no escopo declarado |
| AT-13 | Limiares temporais mudam a visão sem exigir novo evento de domínio. | temporal, stream | VERIFIED no escopo declarado |
| AT-14 | Sucesso produtivo com limpeza pendente não vira tarefa fracassada. | canonical_states | VERIFIED no escopo declarado |
| AT-15 | UI teclado/foco/leitores de tela/light-dark e textos longos sem execução de HTML. | accessible, untrusted | VERIFIED no escopo declarado |
| AT-16 | Consulta em lote não cresce em N+1 por ocorrência/agente. | projection | VERIFIED no escopo declarado |
| OB-01 | Fonte vinculada somente a agente/workspace autorizado. | registration, audience | VERIFIED no escopo declarado |
| OB-02 | Token de observação rejeitado em mensagens, handoffs, MCP, runtime e emissão de tickets. | audience | VERIFIED no escopo declarado |
| OB-03 | EPT de leitura não ganha permissão de publicar telemetria. | audience | VERIFIED no escopo declarado |
| OB-04 | Agente B não publica estado para A por campo no payload. | registration, audience | VERIFIED no escopo declarado |
| OB-05 | Mesmo seq/hash não duplica evento nem renova validade. | replay | VERIFIED no escopo declarado |
| OB-06 | Mesmo seq com conteúdo diferente conflita; seq antiga não sobrescreve. | replay | VERIFIED no escopo declarado |
| OB-07 | Geração anterior não atualiza instância nova; reset local não remove fencing. | replay | VERIFIED no escopo declarado |
| OB-08 | Relógios atrasado/futuro e backlog após reconnect não tornam dado antigo atual. | freshness, herdr_contract | VERIFIED no escopo declarado |
| OB-09 | TTL expirado vira observação stale, não idle, offline canônico ou capacidade livre. | freshness, external | VERIFIED no escopo declarado |
| OB-10 | Revogação de fonte/credencial/identidade impede novos reportes/renovação. | audience | VERIFIED no escopo declarado |
| OB-11 | Duas sessões da mesma identidade preservam estados independentes. | registration | VERIFIED no escopo declarado |
| OB-12 | Instâncias Herdr diferentes com mesmo pane-id não colidem. | occupant | VERIFIED no escopo declarado |
| OB-13 | Pane renomeado/movido/substituído respeita evidência de ocupante ou exige reassociação. | occupant | VERIFIED no escopo declarado |
| OB-14 | Done/idle de startup/switch sem completion_ref não gera conclusão fictícia. | completion | VERIFIED no escopo declarado |
| OB-15 | Término observado não conclui handoff nem libera claim/capacidade/inbox. | canonical_isolation | VERIFIED no escopo declarado |
| OB-16 | Reporte blocked não gera aprovação canônica nem permite responder via token observador. | canonical_isolation, audience | VERIFIED no escopo declarado |
| OB-17 | Fonte Herdr desconecta e volta: snapshot reconcilia sem replay produtivo. | herdr_contract, replay | VERIFIED no escopo declarado |
| OB-18 | Schema/versionamento incompatível gera indisponibilidade explícita, sem campos adivinhados. | herdr_contract | VERIFIED no escopo declarado |
| OB-19 | Estado inferido não sobrescreve evento canônico correlacionado do Core. | correlation | VERIFIED no escopo declarado |
| OB-20 | Limites de taxa/tamanho/cardinalidade e falta de disco retornam recusa honesta. | limits | VERIFIED no escopo declarado |
| OB-21 | Fonte maliciosa não injeta HTML, URL executável, prompt, comando ou logs secretos na UI. | untrusted | VERIFIED no escopo declarado |
| OB-22 | Observador Herdr não chama prompt/start/send-keys/focus/kill. | observer_readonly | VERIFIED no escopo declarado |
| OB-23 | Nexus sem Herdr instalado inicia, testa e opera normalmente. | optional, off | VERIFIED no escopo declarado |
| OB-24 | Desativar OBS mantém MCP-only, Core e Connector funcionais. | off | VERIFIED no escopo declarado |

## Limites que não criam novos requisitos

Herdr: Windows0.9.5/protocolo22/schema1, instalação real e ocupantes sintéticos; polling degradado declarado. Correlação: contrato Windows/local/embedded com fonte sem prova mantida separada. Acessibilidade: teclado/foco/estrutura semântica e browser real; não se alega campanha de um leitor de tela específico. Falta de disco: testes de falha/commit comprovam recusa e rollback, sem encher o disco pessoal.

A prova de OBS-off no remoto é complementar ao toggle local; não foi executado um novo toggle remoto nesta auditoria. Campanhas reais de provedor/clientes/serviço e aceites globais permanecem nos respectivos requisitos, sem serem exigidos novamente para regras de passividade, autoridade ou empacotamento.

Quanto a AC-10: reescrever todo histórico Git ou revogar uma chave UAT anterior ao R3 não é requisito literal da ausência de segredos nos artefatos entregues. A correção do snapshot, inventário público e testes de proteção podem sustentar aceite delimitado da entrega; a retenção histórica/validade desconhecida é risco registrado separado. Este trabalho não repete a varredura e não promove AC-10.

## Como verificar a associação

Cada bundle identifica arquivos de produto com hash/símbolos, testes com linhas, assertions e hashes, e um XML aprovado escolhido. Frontend inclui título/assertions/XML; browser e Herdr reais possuem referências e hashes. Falhas históricas e reruns não são removidos nem somados. Algumas assertions de manutenção de versão de migração no fonte atual podem ser posteriores a XML antigo; o relatório identifica a identidade e o escopo histórico, sem fingir nova execução.
