# Matriz unificada de testes e gates R4


**Todos os cenários de produto começam NOT_RUN.** Os cenários TR4 abaixo são especificações a implementar. TN/J mantêm o texto de preparação/resultado do plano original; execução sintética não fecha um requisito explicitamente de provider ou multi-host.


Contagem documental: **164 cenários** = 85 TR4 novos/específicos + 79 TN/J preservados. Não são 164 testes executados.


## Campos mínimos de evidência


test_id, test_node, layer, source_commit, Core/Connector commits, hashes dos wheels/bundle, SO/Python/provider, comando, exit_code, XML/log redigido, resultado observado e blockers. Não somar rerun/subconjunto ao total da suíte.


## TR4 — condições novas ou explicitadas


### TR4-00-01 — Registrar branch, HEAD, fonte e capacidade realmente instalada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.01.

**Preparação:** Clone de laboratório na branch e diretório com alteração não commitada.

**Ação:** Gerar baseline e executar novamente sem editar código.

**Resultado obrigatório:** Mesmo HEAD e alteração local preservados; manifest distingue fonte, wheel e qualificação; nenhuma alteração destrutiva.


### TR4-00-02 — Encerrar planos concorrentes sem perder requisito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.02.

**Preparação:** Planos R3, CN1–CN5 e arquivos de planejamento presentes.

**Ação:** Validar crosswalk e procurar tarefas sem sucessor.

**Resultado obrigatório:** 70 tarefas originais e 79 cenários TN/J possuem destino; nenhuma tarefa está DONE só por estar descrita.


### TR4-00-03 — Fixar responsabilidades e interfaces R4 entre repositórios

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.03.

**Preparação:** Peer de contrato sem provider; payloads válidos e respostas com envelope legado.

**Ação:** Exercitar fixtures de protocolo e comparar representação.

**Resultado obrigatório:** Objetos /v1 diretos são aceitos; ok/data legado não é confundido; divergências produzem VERSION_INCOMPATIBLE antes de efeito.


### TR4-00-04 — Solicitar bundle Core R4 e preservar histórico r3

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.04.

**Preparação:** Bundle r3 fixado e fixtures-alvo R4.

**Ação:** Validar rejeição cruzada e leitura histórica explícita.

**Resultado obrigatório:** R3 não executa efeitos R4; receipts históricos continuam interpretáveis; gate remoto permanece BLOCKED_EXTERNAL até artefato compartilhado.


### TR4-00-05 — Construir harness de testes e limites de evidência

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS00.05.

**Preparação:** Ambiente sem credenciais de providers.

**Ação:** Rodar um controle de fixture e validar o manifesto de evidência.

**Resultado obrigatório:** Campanha pode passar em contrato sem marcar provider/multihost como PASS; segredos de laboratório identificados e isolados.


### TR4-01-01 — Extrair Deps e composição antes de remover transporte

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.01.

**Preparação:** Server atual com /mcp e REST saudável em fixture.

**Ação:** Importar nova composição e comparar catálogo HTTP antes/depois.

**Resultado obrigatório:** HTTP mantém tools/resources e identidade; import não abre listener ou subprocesso; não há dependência do Connector.


### TR4-01-02 — Remover o ramo MCP stdio sem shim

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.02.

**Preparação:** Configuração legada selecionada e captura de stdin/stdout/processos.

**Ação:** Invocar comandos antigos e novas opções HTTP.

**Resultado obrigatório:** Nenhuma sessão MCP stdio nasce; serve continua HTTP; nenhum adaptador nativo é removido por usar stdin/stdout.


### TR4-01-03 — Definir CLI principal e extras de instalação

**Estado:** NOT_RUN. **Camada:** `packaging`. **Tarefa:** NS01.03.

**Preparação:** Wheel em ambiente limpo sem clone irmão.

**Ação:** Executar help, serve-lite e import dos adaptadores.

**Resultado obrigatório:** CLI não inicia stdio sem argumentos; extras contêm o Core necessário e não exigem a aplicação Connector.


### TR4-01-04 — Montar routers /v1 com autenticação específica

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.04.

**Preparação:** Requests HTTP e upgrade local/remoto com chaves/tickets inválidos.

**Ação:** Consultar protocolo público, /me e fazer upgrades positivos/negativos.

**Resultado obrigatório:** Só protocolo público expõe dados não privados; endpoints escopados rejeitam credenciais de audiência errada antes do handler.


### TR4-01-05 — Migrar configuração MCP apenas selecionada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS01.05.

**Preparação:** Arquivo com duas entradas de terceiros e uma Nexus selecionada.

**Ação:** Aplicar migração, repetir e simular edição concorrente.

**Resultado obrigatório:** Somente entrada selecionada muda; key/id intactos; concorrência recusa sem sobrescrever terceiros; stdio não retorna como rollback.


### TR4-02-01 — Definir chaves de escopo imutáveis

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.01.

**Preparação:** Dois Servers/executores com mesmos binding/session/request IDs.

**Ação:** Inserir, consultar e remover um namespace.

**Resultado obrigatório:** Nenhuma colisão ou remoção cruzada; UI pede escopo quando alias curto é ambíguo.


### TR4-02-02 — Criar extensões aditivas e índices

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS02.02.

**Preparação:** Banco vazio e cópia legada consistente.

**Ação:** Migrar, repetir e conferir constraints/índices.

**Resultado obrigatório:** Migrações idempotentes; dados legados e negações preservados; consulta indexada encontra escopo exato.


### TR4-02-03 — Persistir identidade técnica local e remota

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.03.

**Preparação:** Duas inicializações locais e dois pedidos idempotentes de registro remoto.

**Ação:** Reabrir a base e repetir registro com mesma intenção.

**Resultado obrigatório:** IDs estáveis, nenhum Agent novo e nenhum takeover automático por clone de diretório.


### TR4-02-04 — Separar workspace lógico da realização física

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.04.

**Preparação:** Server Linux, fixture de realização Windows e duas pastas do mesmo repo.

**Ação:** Preparar vínculos lógicos e tentar falsa equivalência.

**Resultado obrigatório:** Nenhuma resolução de filesystem remoto em A; associação depende de permissão e aprovação explícita; histórico não é re-hasheado.


### TR4-02-05 — Implementar writers transacionais e readers de histórico

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS02.05.

**Preparação:** Instrumentação da connection factory e peer que bloqueia I/O.

**Ação:** Admitir operação e bloquear o dispatcher externo.

**Resultado obrigatório:** Commit termina antes do I/O; consultas continuam responsivas e reproduzem os registros por IDs exatos.


### TR4-03-01 — Implementar /me pela autoridade já existente

**Estado:** NOT_RUN. **Camada:** `contract_scale`. **Tarefa:** NS03.01.

**Preparação:** 100 mil registros sintéticos com índice por key hash.

**Ação:** Autenticar uma key e enviar hint de outro agente.

**Resultado obrigatório:** Lookup escopado/indexado; spoof recusado; nenhum cadastro ou rotação ocorre.


### TR4-03-02 — Implementar proposta/aplicação com política herdada

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.02.

**Preparação:** Agente com negação explícita e operador de fixture.

**Ação:** Tentar self-escalation e depois aprovação autorizada.

**Resultado obrigatório:** Agente não autoaprova; operador aplica uma revisão; repetição retorna a mesma proposta aplicada sem gerar outra identidade.


### TR4-03-03 — Emitir tickets escopados e revogáveis

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.03.

**Preparação:** Dois bindings/agentes, dois executores e relógio controlado.

**Ação:** Reusar ticket em outro alvo, expirar e rotacionar key.

**Resultado obrigatório:** Alvo/audiência/epoch incorretos recusados; outro agente permanece operacional; novo ticket não revive key revogada.


### TR4-03-04 — Implementar capability MCP de sessão com audiência própria

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.04.

**Preparação:** Harness HTTP de laboratório com token de sessão e ticket NXL.

**Ação:** Chamar tool permitida, proibida e depois revogar sessão.

**Resultado obrigatório:** Só ações permitidas têm efeito; ticket errado falha; revogação bloqueia MCP sem depender de proxy Connector.


### TR4-03-05 — Gerar comando protegido e não recuperar hash como segredo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS03.05.

**Preparação:** Agente hash-only e captura de issue_key/argv.

**Ação:** Gerar comando em Bash e PowerShell e usar key existente.

**Resultado obrigatório:** Comando sem segredo de longa duração; nenhuma chamada de emissão; MCP anterior continua autenticando o mesmo agente.


### TR4-04-01 — Consumir catálogo sem compor runtime falso

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.01.

**Preparação:** Ambiente sem harnesses e Core instalado.

**Ação:** Consultar catálogo antes de iniciar journal/runtime.

**Resultado obrigatório:** Catálogo vem do Core sem spawn/porta/credencial; attach continua registrado não qualificado.


### TR4-04-02 — Preservar candidatos e avaliar no host correto

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.02.

**Preparação:** Par Node/CLI de laboratório e duas versões da mesma família.

**Ação:** Discovery → avaliação → serialização.

**Resultado obrigatório:** Refs/build/version/architecture preservados; avaliação remota utiliza host remoto; nenhum provider é iniciado para listar.


### TR4-04-03 — Gerar e ingressar revisão completa do inventário

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.03.

**Preparação:** Mesmos paths/versão com bytes alterados e inventário reordenado.

**Ação:** Publicar snapshots repetidos, adulterados e antigos.

**Resultado obrigatório:** Bytes/qualificação alterados mudam revisão; reorder/timestamp isolado não muda; stale/adulterado recusados antes de binding.


### TR4-04-04 — Expor opções com estados técnicos e canônicos separados

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.04.

**Preparação:** Executor offline, candidato unqualified e agente sem autorização.

**Ação:** Consultar opções e comparar estados.

**Resultado obrigatório:** UI recebe razões verdadeiras; nenhuma combinação bloqueante habilita start; dados de outro executor não são apresentados ao principal errado.


### TR4-04-05 — Resolver instalação da revisão exibida

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS04.05.

**Preparação:** Duas cópias byte-idênticas A/B e revisão inicial.

**Ação:** Selecionar B, reordenar e depois alterar B antes do apply.

**Resultado obrigatório:** B continua B após reorder; drift/stale recusa antes de efeito; ref legada ambígua exige reseleção.


### TR4-05-01 — Registrar realização no executor proprietário

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.01.

**Preparação:** Realização Windows remota e Server sem esse path.

**Ação:** Registrar e tentar usar ref em outro executor/agente.

**Resultado obrigatório:** Somente escopo correto resolve; Server não testa filesystem remoto; nenhum spawn ao preparar.


### TR4-05-02 — Compor proposta agregada de vínculo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.02.

**Preparação:** Primeiro uso local/remoto com opções inequívocas.

**Ação:** Preparar proposta pela mesma API usada pela UI.

**Resultado obrigatório:** Uma confirmação mostra agente, host, instalação, projeto e escopo; backend já resolveu detalhes técnicos.


### TR4-05-03 — Aplicar proposta com CAS e recibo recuperável

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.03.

**Preparação:** Falha de resposta depois de commit e alteração concorrente de perfil.

**Ação:** Repetir client_intent_id e depois tentar proposta obsoleta.

**Resultado obrigatório:** Sem duplicação; resposta recupera mesmo binding; mudança de escopo exige nova aprovação.


### TR4-05-04 — Implementar reuso e novo processo explícito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.04.

**Preparação:** Duas sessões/candidatos e uma operação de open incerta.

**Ação:** Pedir start repetido, novo explícito e caso ambíguo.

**Resultado obrigatório:** Reuso não cria processo; new_session autorizado é distinto; unknown/ambiguidade não escolhe substituto.


### TR4-05-05 — Tratar drift e login de provider como estados explícitos

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS05.05.

**Preparação:** Atualização de binário, root movido e provider sem login.

**Ação:** Iniciar pela API e rebind após consentimento.

**Resultado obrigatório:** Recusas anteriores ao efeito têm diagnóstico; rebind efetivo preserva agente/key e não desliga outra sessão.


### TR4-06-01 — Implementar resolve sem executar

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.01.

**Preparação:** Peer contador de chamadas nativas e resposta perdida de resolve.

**Ação:** Resolver duas vezes mesma intenção e consultar por client_intent_id.

**Resultado obrigatório:** Zero efeitos; mesmos IDs; body diferente conflita; consulta recupera resposta perdida.


### TR4-06-02 — Admitir operação e outbox atomicamente

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.02.

**Preparação:** Injeções antes/depois de commit.

**Ação:** Admitir, perder resposta e repetir chave.

**Resultado obrigatório:** Uma operação/outbox lógica e um claim; falha pré-commit não anuncia sucesso; pós-commit é consultável.


### TR4-06-03 — Implementar dispatcher com reserva e revalidação

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.03.

**Preparação:** Fila pequena saturada e rotação durante espera.

**Ação:** Enfileirar submits e um controle, alterar grant antes do despacho.

**Resultado obrigatório:** Controle progride; operação obsoleta produz zero efeito; quota volta exatamente a zero ao concluir.


### TR4-06-04 — Separar dispatch, receipt e consulta

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS06.04.

**Preparação:** Peer registra uma execução e perde ACK do receipt.

**Ação:** Reenviar receipt idêntico e consultar operação.

**Resultado obrigatório:** Receipt idempotente não cria trabalho; um efeito máximo por intenção demonstrada; unknown não é retry seguro por timeout.


### TR4-06-05 — Preservar consumo exclusivo e causalidade do domínio

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS06.05.

**Preparação:** Mesma delivery disputada por MCP e dois runtimes.

**Ação:** Concorrer claim e encerrar um turno sem handoff_complete.

**Resultado obrigatório:** Um executor lógico; observers não executam; handoff permanece pendente até caso de uso governado.


### TR4-07-01 — Compor stores e runtime por ownership explícito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.01.

**Preparação:** Dois starts concorrentes e cancelamento de um waiter.

**Ação:** Compor instâncias e contar stores/workers/reservas.

**Resultado obrigatório:** Uma inicialização possuída por store; nenhum worker órfão; quota física agregada respeitada.


### TR4-07-02 — Adaptar prepare/open/control preservando IDs

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS07.02.

**Preparação:** Core real + peer nativo e contextos válidos/invalidos.

**Ação:** Executar open/submit/steer/interrupt/close pelo Server.

**Resultado obrigatório:** IDs conservados e erros tipados; operação legítima funciona; scope/generation errados não alcançam peer.


### TR4-07-03 — Gerar ambiente e cliente MCP por abertura

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.03.

**Preparação:** Duas sessões e dois Servers com IDs longos semelhantes.

**Ação:** Preparar lançamento e inspecionar env/arquivos reais de laboratório.

**Resultado obrigatório:** Configurações distintas, URL correta, tokens por sessão; marker estrangeiro impede sobrescrita; nenhum MCP proxy.


### TR4-07-04 — Compor aprovação e bridge Pi por portas públicas

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS07.04.

**Preparação:** Core real e bridges de laboratório sem provider.

**Ação:** Invocar pedido nativo, ação Pi limitada e tentativa fora de escopo.

**Resultado obrigatório:** Ação canônica passa pelo guard; fora de escopo recusa; capability não implementada é explicitamente indisponível.


### TR4-07-05 — Ligar eventos e encerramento ao host persistente

**Estado:** NOT_RUN. **Camada:** `core_fault_injection`. **Tarefa:** NS07.05.

**Preparação:** Open tardio, close bloqueado e release pendente.

**Ação:** Cancelar waiter, iniciar shutdown e restaurar backend.

**Resultado obrigatório:** Mesma abertura/handle permanece alcançável; controles independentes; consultas relatam físico e durável separadamente.


### TR4-08-01 — Autenticar upgrade e negociar versão antes de efeitos

**Estado:** NOT_RUN. **Camada:** `transport_contract`. **Tarefa:** NS08.01.

**Preparação:** Peers válidos e ticket cruzado, expirado ou versão antiga.

**Ação:** Tentar upgrades e enviar operation antes do welcome.

**Resultado obrigatório:** Somente namespace/protocolo correto progride; zero efeito em negociação inválida; secrets ausentes do log.


### TR4-08-02 — Confirmar attach explicitamente e isolar agentes

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.02.

**Preparação:** Dois agentes e attach antigo bloqueado durante rotação.

**Ação:** Admitir A/B, rotacionar A e liberar resposta velha.

**Resultado obrigatório:** B permanece válido; A só abre sob ACK novo; ticket A não concede B; ausência de ACK mantém PENDING.


### TR4-08-03 — Implementar reconciliação e readiness por sessão

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.03.

**Preparação:** Journal indisponível e depois recuperado.

**Ação:** Concluir handshake, simular falha e restaurar.

**Resultado obrigatório:** Operação nova fica bloqueada até recuperação; controles/história permitidos conforme escopo; nenhuma falsificação de liveness.


### TR4-08-04 — Validar escopo de todos os frames

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS08.04.

**Preparação:** Canal B pede receipt/approval/session de A com IDs iguais.

**Ação:** Percorrer receiver→handler→repo/Core de laboratório.

**Resultado obrigatório:** Zero dados/efeitos estrangeiros; caso legítimo passa; consultas durante handshake não ganham scope adicional.


### TR4-08-05 — Controlar filas, watchdog e cancelamento do link

**Estado:** NOT_RUN. **Camada:** `transport_fault_injection`. **Tarefa:** NS08.05.

**Preparação:** Flood, peer silencioso e queda durante execução.

**Ação:** Saturar e mandar interrupt/revoke/ACK; reconectar.

**Resultado obrigatório:** Memória/pendências limitadas; controles progridem; receipt é recuperado por ID sem duplicar trabalho.


### TR4-09-01 — Despachar remote open por realização aprovada

**Estado:** NOT_RUN. **Camada:** `cross_repo_contract`. **Tarefa:** NS09.01.

**Preparação:** Server sem binários e Connector peer com Core/realização local.

**Ação:** Abrir remotamente sem CLI ter criado sessão antes.

**Resultado obrigatório:** Um open com mesmo ID em Core; Server não acessa filesystem B; modo não suportado recusa antes de spawn.


### TR4-09-02 — Instalar lease inicial e renovar com correlação

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.02.

**Preparação:** Relógios independentes, RTT alto e resposta duplicada.

**Ação:** Solicitar initial/renew/reconnect e atrasar resposta.

**Resultado obrigatório:** Replay não estende deadline; resposta tardia não permite efeito; gerações/revisões correspondem ao grant legítimo.


### TR4-09-03 — Completar matriz de verbos e targeting

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.03.

**Preparação:** Adapters de contrato com targeting distinto.

**Ação:** Exercitar cada verbo anunciado e verbos não suportados.

**Resultado obrigatório:** Somente capacidades reais passam; expected_turn preservado; operação desconhecida gera erro tipado antes do efeito.


### TR4-09-04 — Revogar sem troca silenciosa de ownership

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS09.04.

**Preparação:** Dois canais/executores concorrentes e um turno desconhecido.

**Ação:** Avançar generation, revogar A e tentar execução antiga em B.

**Resultado obrigatório:** Contexto obsoleto recusado; nenhum processo substituto; histórico continua consultável no scope autorizado.


### TR4-09-05 — Qualificar desconexão de controle e ferramentas separadamente

**Estado:** NOT_RUN. **Camada:** `cross_repo_integration`. **Tarefa:** NS09.05.

**Preparação:** Dois canais controlados e uma conversa tools-only.

**Ação:** Derrubar canais individualmente e expirar capability.

**Resultado obrigatório:** Sem bypass/replay de tool mutável; tools-only legítimo permanece independente; runtime gerenciado respeita sua autorização.


### TR4-10-01 — Ingressar evento com deduplicação e watermark contíguo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.01.

**Preparação:** Seq1/seq3, duplicata1 e duplicata com hash diferente.

**Ação:** Ingressar lote e perder conexão antes/depois de commit.

**Resultado obrigatório:** Watermark só chega a1 até seq2; duplicata legítima não duplica projeção; conflito de hash é explícito.


### TR4-10-02 — Separar leitura finita de follower contínuo

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS10.02.

**Preparação:** Um evento real persistido e nenhum posterior.

**Ação:** Pedir página e publicar sem produzir outro evento.

**Resultado obrigatório:** Página termina; seq1 é enviada prontamente; próximo snapshot vazio não prende o request.


### TR4-10-03 — Usar target correto e aplicar ACK local uma vez

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.03.

**Preparação:** ACK1 conhecido, lote2 sem ACK2 e replay1.

**Ação:** Aguardar dois alvos e injetar falha em Core acknowledge.

**Resultado obrigatório:** Replay1 conclui; batch2 aguarda; obrigação de aplicar ACK converge sem novo send_turn.


### TR4-10-04 — Recuperar publicador sem evento novo

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS10.04.

**Preparação:** Primeira leitura falha e journal contém seq1.

**Ação:** Restaurar storage e sinalizar reconnect sem publish novo.

**Resultado obrigatório:** Task é retomada uma vez, seq1 publicada/confirmada, payloads offline não crescem ilimitadamente em RAM.


### TR4-10-05 — Preservar projeções canônicas e retenção

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS10.05.

**Preparação:** Eventos fora de ordem, terminal cedo e UI offline.

**Ação:** Ingressar e reconstruir projeções duas vezes.

**Resultado obrigatório:** Estado idempotente e auditável; ACK não depende UI; handoff/causalidade continuam íntegros.


### TR4-11-01 — Persistir proposta operacional separada de exibição

**Estado:** NOT_RUN. **Camada:** `core_integration`. **Tarefa:** NS11.01.

**Preparação:** Pedido real observado no journal Core e pipeline de ingresso/UI.

**Ação:** Receber, redigir para tela e recuperar pedido operacional.

**Resultado obrigatório:** Hash/JSON operacional byte-semanticamente preservados; UI não vaza secrets; dois namespaces não se sobrescrevem.


### TR4-11-02 — Autorizar operador e aplicar CAS antes do efeito

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.02.

**Preparação:** Operador válido, agente solicitante e duas decisões concorrentes.

**Ação:** Tentar approve sem autoridade e CAS concorrente approve/deny.

**Resultado obrigatório:** Sem autoridade zero operação nativa; uma decisão canônica vence; perdedora recebe conflito consultável.


### TR4-11-03 — Despachar aplicação única e traduzir pelo contrato

**Estado:** NOT_RUN. **Camada:** `cross_repo_contract`. **Tarefa:** NS11.03.

**Preparação:** Server→Connector→Core reais nas fronteiras de laboratório.

**Ação:** Decidir pedido e repetir resposta HTTP/notificação.

**Resultado obrigatório:** Uma aplicação por operation_id; request/turn/scope corretos; accept/decline legítimos passam e pedido velho não afeta turno novo.


### TR4-11-04 — Conservar producers, recibos e incerteza de decisão

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.04.

**Preparação:** POST recebido bloqueado, cancelamento IPC e write nativo incerto.

**Ação:** Cancelar waiter, consultar e restaurar backend.

**Resultado obrigatório:** Producer permanece ou resultado é classificado; mesma decisão converge; nenhuma execução duplicada ou estado pending fictício.


### TR4-11-05 — Tratar input sensível e administrativo explicitamente

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS11.05.

**Preparação:** Pedido input, administrative e native session inexistente.

**Ação:** Decidir, expirar e simular crash antes da aplicação.

**Resultado obrigatório:** Limite de recuperação declarado; nenhuma resposta inventada ou desvio de namespace; consultar decisão não revela conteúdo sensível.


### TR4-12-01 — Unificar acesso MCP e native-actions no domínio

**Estado:** NOT_RUN. **Camada:** `domain_integration`. **Tarefa:** NS12.01.

**Preparação:** Uma delivery concorrida por MCP, local e Pi remoto.

**Ação:** Solicitar claim/complete via caminhos distintos.

**Resultado obrigatório:** Um claimant lógico; repeat é idempotente; policy/delivery budget preservados.


### TR4-12-02 — Aplicar autorização da sessão ao MCP HTTP

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.02.

**Preparação:** Capability limitada e key tools-only do mesmo agente.

**Ação:** Testar tool permitida, negada, root outro e revoke.

**Resultado obrigatório:** Mesmo agente, scopes diferentes; managed não contorna lease; tools-only não depende do WSS.


### TR4-12-03 — Preservar causalidade e resultado governado

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.03.

**Preparação:** Turno final sem complete e cadeia de replies próxima do limite.

**Ação:** Reconectar e completar explicitamente.

**Resultado obrigatório:** Sem complete automático nem aumento do orçamento causal; destinatário e evidência preservados.


### TR4-12-04 — Publicar capacidades apenas demonstradas

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.04.

**Preparação:** Runtime conversacional sem tool path e outro com ponte válida.

**Ação:** Consultar opções/capacidades e despachar trabalho governado.

**Resultado obrigatório:** Primeiro não recebe execute_work; segundo segue grant/claim; nenhum false READY por metadado estático.


### TR4-12-05 — Manter superfície MCP compacta

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS12.05.

**Preparação:** Catálogo com poucos e muitos executores, mesma toolset.

**Ação:** Comparar nomes/schema e executar preflight HTTP.

**Resultado obrigatório:** Número de ferramentas não cresce por host; orientação compatível com identidade/workspace e sem stdio.


### TR4-13-01 — Implementar seleção executor→instalação→workspace

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.01.

**Preparação:** Duas cópias idênticas e Server Linux com executor Windows.

**Ação:** Selecionar B e alterar snapshot no peer API.

**Resultado obrigatório:** UI mantém alvo correto quando válido e recusa stale; fatos remotos não são reavaliados pelo OS do Server.


### TR4-13-02 — Substituir configuração técnica por consentimento agregado

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.02.

**Preparação:** Primeiro uso e uso recorrente local/remoto.

**Ação:** Concluir wizard duas vezes com mesmo binding.

**Resultado obrigatório:** Segundo uso reutiliza sem chave/JSON manual; local não exige Connector; remoto não pede provider secret ao Server.


### TR4-13-03 — Implementar acompanhamento por IDs e estados honestos

**Estado:** NOT_RUN. **Camada:** `ui_integration`. **Tarefa:** NS13.03.

**Preparação:** Resposta perdida após admissão e evento terminal posterior.

**Ação:** Operar UI e reconectar SSE.

**Resultado obrigatório:** Mesmo ID reaparece e estado converge sem segundo start; UI offline não altera ACK durável.


### TR4-13-04 — Concluir CLI humana/headless e logs observadores

**Estado:** NOT_RUN. **Camada:** `cli_integration`. **Tarefa:** NS13.04.

**Preparação:** Ambiguidade de aliases e prompt desabilitado.

**Ação:** Executar start/status/logs/stop com timeouts.

**Resultado obrigatório:** Erros estáveis e ação corretiva; identidade correta; follower termina sem matar runtime.


### TR4-13-05 — Expor diagnóstico e aprovações sem vazar dados

**Estado:** NOT_RUN. **Camada:** `ui_security`. **Tarefa:** NS13.05.

**Preparação:** Usuário de teste autorizado e agente com leitura restrita.

**Ação:** Consultar views/log/export e responder pedido por UI.

**Resultado obrigatório:** Scopes/reasons úteis sem secrets; canal de apresentação não torna agente seu próprio aprovador.


### TR4-14-01 — Recuperar histórico antes de admitir após restart

**Estado:** NOT_RUN. **Camada:** `restart_integration`. **Tarefa:** NS14.01.

**Preparação:** Receipt real em disco, processo aplicativo novo e binário removido.

**Ação:** Reiniciar host e consultar client intent/operation/session.

**Resultado obrigatório:** Histórico responde; ownership desconhecido permanece; nenhum novo spawn para recuperar dados.


### TR4-14-02 — Invalidar autoridade em todas as superfícies

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS14.02.

**Preparação:** CAS perdido para geração mais nova e ACK perdido após revoke.

**Ação:** Consultar, tentar submit antigo e recuperar storage.

**Resultado obrigatório:** Contexto antigo zero efeito; rollback comprovado recupera disponibilidade; verdadeiramente unknown continua restrito.


### TR4-14-03 — Implementar shutdown DRAINING_PENDING com orçamento único

**Estado:** NOT_RUN. **Camada:** `core_fault_injection`. **Tarefa:** NS14.03.

**Preparação:** Dois runtimes, open tardio, close travado e release pendente.

**Ação:** Parar Server e depois restaurar backend.

**Resultado obrigatório:** Prazo público limitado; ambos relatados; força não espera storage; segunda recuperação alcança mesmos owners sem duplicação.


### TR4-14-04 — Aplicar quotas e cache limitados com medições

**Estado:** NOT_RUN. **Camada:** `load`. **Tarefa:** NS14.04.

**Preparação:** Base sintética e flood de um executor com outro legítimo.

**Ação:** Medir lookup/memória/filas e enviar controle sob carga.

**Resultado obrigatório:** Sem full enumeration por onboarding; memória bounded; controles e outro agente progridem; resultados e hardware registrados.


### TR4-14-05 — Testar falhas de processo e limites de plataforma

**Estado:** NOT_RUN. **Camada:** `os_backend`. **Tarefa:** NS14.05.

**Preparação:** Backend real disponível ou bloqueio documentado.

**Ação:** Matar supervisor de laboratório e observar árvore própria.

**Resultado obrigatório:** Apenas ownership comprovado é controlado; backend ausente é BLOCKED/NOT_RUN, não PASS universal.


### TR4-15-01 — Executar M0–M3 com preservação e retomada

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS15.01.

**Preparação:** Snapshot legado com endpoints negados, jobs históricos e keys.

**Ação:** Interromper backfill e retomar duas vezes.

**Resultado obrigatório:** Mesmos IDs/negações/conteagens; batches convergem; nenhuma migração abre processo.


### TR4-15-02 — Drenar owner antigo antes de trocar execução

**Estado:** NOT_RUN. **Camada:** `migration_runtime`. **Tarefa:** NS15.02.

**Preparação:** Sessão antiga ativa e outra com resultado incerto.

**Ação:** Executar cutover controlado e tentar abrir substituto.

**Resultado obrigatório:** Ativa encerra pelo mecanismo correto; unknown não duplica; rollback não reativa stdio.


### TR4-15-03 — Remover loaders/codecs duplicados depois de paridade

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS15.03.

**Preparação:** Busca estática de imports/Popen e testes de comportamento local.

**Ação:** Executar verificação de fronteiras e paridade delimitada.

**Resultado obrigatório:** Runtime físico só existe no Core; domínio e HTTP MCP preservados; nenhum import da aplicação Connector.


### TR4-15-04 — Migrar configuração e documentar rollback seguro

**Estado:** NOT_RUN. **Camada:** `migration`. **Tarefa:** NS15.04.

**Preparação:** Falha de apply e tree com marker de outro binding.

**Ação:** Aplicar/repetir/migrar configuração e ensaiar restore.

**Resultado obrigatório:** Config alheia intacta; rollback recusado quando inseguro; histórico e operações unknown preservados.


### TR4-15-05 — Atualizar documentação e instruções operacionais

**Estado:** NOT_RUN. **Camada:** `unit_contract`. **Tarefa:** NS15.05.

**Preparação:** README/help/resources/dashboard atualizados.

**Ação:** Comparar docs com APIs e matriz de capacidade.

**Resultado obrigatório:** Nenhum comando fictício apresentado como existente; docs não contradizem gate/qualificação e negações.


### TR4-16-01 — Construir artefatos imutáveis e contratos instalados

**Estado:** NOT_RUN. **Camada:** `packaging`. **Tarefa:** NS16.01.

**Preparação:** Ambiente isolado sem fonte no sys.path.

**Ação:** Instalar e executar smoke público.

**Resultado obrigatório:** Hashes/versões registrados; serve-lite funcional sem torch novo; nenhum schema é obtido remotamente em execução.


### TR4-16-02 — Executar conjunto completo de regressões sem inflar números

**Estado:** NOT_RUN. **Camada:** `regression_suite`. **Tarefa:** NS16.02.

**Preparação:** Ambiente atual e fixtures de fault injection.

**Ação:** Rodar duas vezes casos de corrida e uma suíte completa.

**Resultado obrigatório:** Resultados por camada/node/versão; nenhum PASS sem execução; falha externa distinguida de defeito funcional.


### TR4-16-03 — Qualificar ciclo local sem Connector instalado

**Estado:** NOT_RUN. **Camada:** `provider_local`. **Tarefa:** NS16.03.

**Preparação:** Um SO/provider autorizado e pacote Nexus/Core apenas.

**Ação:** Executar caminho local ponta a ponta.

**Resultado obrigatório:** Mesmo adapter Core; nenhum Connector/WSS local obrigatório; governança e shutdown demonstrados.


### TR4-16-04 — Qualificar ciclo remoto heterogêneo

**Estado:** NOT_RUN. **Camada:** `multi_host`. **Tarefa:** NS16.04.

**Preparação:** Topologia A/B/C autorizada com ao menos um Windows/Unix pertinente.

**Ação:** Executar J01–J34 e TR4 correspondentes com artefatos exatos.

**Resultado obrigatório:** Nenhum filesystem remoto resolvido em A, nenhuma execução duplicada, mesmos IDs; limitações de provider/SO explícitas.


### TR4-16-05 — Emitir decisão por escopo e handoff final

**Estado:** NOT_RUN. **Camada:** `release_review`. **Tarefa:** NS16.05.

**Preparação:** Todas as evidências anteriores e casos NOT_RUN remanescentes.

**Ação:** Revisar cada gate e requisito original preservado.

**Resultado obrigatório:** Decisão proporcional, sem ambiguidades; outro agente consegue instalar artefato e repetir campanha sem inferir campos/rotas.


### TN-01 — Baseline

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS00.05.

**Preparação:** Executar build/testes existentes no HEAD efetivo e comparar com referência.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Falhas anteriores separadas; novos testes de regressão rastreados.


### TN-02 — Crosswalk

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS00.05.

**Preparação:** Comparar dois planos antigos, PR34 e remote-executors com G01–G20.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Todo requisito preservado/substituído/descartado tem justificativa; sem dois backlogs concorrentes.


### TN-03 — Migração nova/legada

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Aplicar migrações em DB vazio e snapshot legado, repetir e interromper backfill.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Retomada idempotente; agent/workspace IDs e histórico preservados.


### TN-04 — Contrato único

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Alterar hash/schema de consumidor e tentar major incompatível.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CI/negociação detecta divergência antes de efeitos.


### TN-05 — Boundary

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS02.05.

**Preparação:** Importar Server sem Connector/provider local; inspecionar árvore de imports.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Server funciona; física nativa só no Core e sem ciclos de dependência.


### TN-06 — Identidade chave

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Autenticar A e enviar hint/payload com agent_id B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Negação antes de bind/spawn; nenhum Agent criado ou identidade alterada.


### TN-07 — Importação sem rotação

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Configurar Connector com chave já usada por MCP; chamar MCP novamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma identidade e chave continuam válidas; issue_key não é acionado.


### TN-08 — Revogação e dois canais

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Rotacionar/revogar key e capability MCP HTTP com WSS/HTTP ativos ou particionados separadamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Invalidação/expiry bloqueiam efeitos da sessão em qualquer caminho; tickets NXL não ampliam escopo MCP.


### TN-09 — Self permission

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS03.05.

**Preparação:** Agente autenticado tenta bind/grant de outro ou habilitar método negado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Políticas existentes preservadas; nenhum autoapprove de escalada.


### TN-10 — Local nativo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Instalar Nexus + Core, sem aplicação Connector, e abrir Codex qualificado local.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Serve hospeda executor e controla runtime sem WSS/pareamento local.


### TN-11 — Owner local

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Duas CLIs e cliente MCP HTTP pedem abertura com mesma chave idempotente; fechar clientes.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Owner único e execução idempotente; runtimes independentes continuam, sem processo MCP stdio.


### TN-12 — Shutdown Server

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS07.05.

**Preparação:** Encerrar serve com runtime próprio e alvo externo anexado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core drena/encerra árvore própria e desanexa externo; relatório por sessão.


### TN-13 — Path remoto

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Server Linux recebe vínculo de diretório Windows validado pelo Connector.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Nenhum realpath/isdir local sobre path remoto; identidade lógica correta.


### TN-14 — Workspace equivalência

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Mesmo Git/path em hosts diferentes e manifesto falsificado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Não mescla/autoriza automaticamente; binding explícito e escopado.


### TN-15 — Setup sem argv

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Selecionar binários Codex/Pi com espaços via UI normal.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core adiciona argumentos obrigatórios; usuário não edita JSON.


### TN-16 — Reuso e drift

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS05.05.

**Preparação:** Repetir start aprovado, depois trocar root/binário/permissão.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro reutiliza; mudança relevante exige reprepare/approval, não expansão silenciosa.


### TN-17 — Canal WSS

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Negociar TLS/protocolo com peer e depois Connector real.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Saída remota bidirecional, sem callback/porta entrante no host.


### TN-18 — Lanes

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Autenticar lane A; tentar operações B; anexar B com própria prova.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** B só disponível após ticket válido; revoke A não empresta sua autoridade a B.


### TN-19 — Instâncias concorrentes

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Abrir canais conflitantes da mesma instalação e reenviar geração antiga.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CAS/fencing impede dois owners ativos ou takeover silencioso.


### TN-20 — Controle sob carga

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS08.05.

**Preparação:** Inundar texto enquanto chega interrupt/revoke.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Limites/priority preservam controle; métricas de fila em bytes disponíveis.


### TN-21 — Idempotência

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Repetir operation_id/hash e depois alterar payload.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro devolve recibo sem efeito novo; segundo OPERATION_CONFLICT.


### TN-22 — ACK durável

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Cair antes/depois do commit de evento e antes do ACK.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Replay deduplicado; watermark só confirma persistido.


### TN-23 — Unknown

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Perder confirmação depois de write possível no harness.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** OUTCOME_UNKNOWN consultável; nenhum novo turno/host automático.


### TN-24 — Consumo exclusivo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** MCP pull, runtime local e remoto competem pela mesma entrega.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um consumidor de execução; outbox não cria outra tarefa.


### TN-25 — Eventos fora de ordem

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS10.05.

**Preparação:** Terminal chega antes de ACK, duplicatas/gaps/geração antiga.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Reducer conserva fatos; gaps explícitos; histórico não autoriza novo efeito.


### TN-26 — Ferramentas canônicas

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Executar via MCP HTTP direto local/remoto e bridge nativa não MCP com o mesmo agente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmos casos de uso/grants/claims e auth; nenhum proxy/fachada MCP no caminho.


### TN-27 — Handoff

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Finalizar turno sem complete governado e depois emitir complete válido.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Primeiro não completa handoff; segundo preserva evidência/correlação/budget.


### TN-28 — HITL

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS12.05.

**Preparação:** Duas interfaces decidem, chega decisão tardia e agente tenta se autoaprovar.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** CAS único, turno/request corretos e autoridade existente exigida.


### TN-29 — MCP HTTP e remoção stdio

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Upgrade com MCP HTTP e antiga entrada Nexus stdio selecionada; invocar entrypoint removido.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** HTTP preservado; migração orientada sem key nova; stdio ausente/erro prescritivo sem transporte ou shim; outras entradas intactas.


### TN-30 — Superfície compacta

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Comparar catálogo/schema/tokens com baseline e adicionar muitos hosts.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Catálogo não replica tools por conexão; diferença justificada/medida.


### TN-31 — CLI consistente

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS01.05.

**Preparação:** Start/status/interrupt/stop/logs com JSON e timeout.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmo domínio/recibo da API; timeout de espera não reenfileira efeito.


### TN-32 — UI primeiro/segundo uso

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Completar fluxo local e remoto duas vezes.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem endpoint/profile/JSON/token manual recorrente; escopo compreensível.


### TN-33 — Modo explícito

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Escolher tools-only, managed e attach.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** UI informa sessão criada/reutilizada/anexada; não promete adotar conversa atual.


### TN-34 — Estados honestos

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS13.05.

**Preparação:** Daemon online, provider ausente, approval pendente e resultado unknown.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Cada condição aparece distintamente; nenhuma marcada como runtime pronto.


### TN-35 — Input hostil

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Enviar paths/plugins/argv/env e identidade forjados pelo wire.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Validação/autoridade impede execução/configuração fora do binding.


### TN-36 — Partição/lease

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Desconectar runtime durante revoke; alterar relógio; restaurar canal.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem novas autorizações offline; limite de lease respeitado e reconciliação anterior à admissão.


### TN-37 — Secrets

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS14.05.

**Preparação:** Inspecionar logs/UI/exports/headers de erro/métricas.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem chave/ticket/provider secret; cardinalidade de labels limitada.


### TN-38 — 100 mil identidades

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Sem provider, popular 100 mil agentes e conectar um por chave.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Lookup indexado e retorno escopado; nenhuma enumeração global ou thread por agente.


### TN-39 — Cache bounded

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Exercer muitas chaves e revogar em cache; simular churn.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Memória limitada e invalidação síncrona; epoch não permanece autorizado.


### TN-40 — Rollback dados

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS15.05.

**Preparação:** Restaurar snapshot/versão suportada após backfill e execução controlada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Dados e políticas preservados; rollback inseguro recusado/explicado.


### TN-41 — Build limpo

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Instalar wheel Nexus serve/serve-lite e Core fixado sem clones irmãos.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Assets/dependências corretos e modo local disponível.


### TN-42 — Server sem harnesses

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Subir A sem binários, provider keys ou diretórios de B/C.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** API/recepção remota funcionam; não solicita instalação local de provider.


### TN-43 — Multihost

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Executar campanha J com A/B/C e mesmo Core wheel.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Controles/eventos/HITL e identidade independem do host central.


### TN-44 — Fault conjunto

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Executar partições, crash e ACK perdido nos três artefatos reais.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Resultados correspondem a efeitos possíveis e sem execução duplicada.


### TN-45 — Release gate

**Estado:** NOT_RUN. **Camada:** `legacy_acceptance`. **Tarefa:** NS16.05.

**Preparação:** Revisar evidências com SHAs/versões e casos ainda NOT_RUN.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Somente capacidades demonstradas qualificadas; bloqueios externos explícitos.


### J01 — Identidade canônica

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Criar agente previamente no Nexus e configurar MCP com sua key; importar a mesma no Connector.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Nenhum segundo Agent/user; MCP continua válido, mesmo agent_id em mensagens e sessões.


### J02 — Não rotacionar para conectar

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Usar Server que guarda somente hash; gerar comando para identidade existente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Comando pede/importa key existente de forma protegida; não chama issue_key silenciosamente.


### J03 — Autenticação errada

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Key A com hint B; depois ticket A tenta abrir lane de B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Negação antes de configuração/spawn; nenhuma atribuição por payload.


### J04 — Nexus local puro

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Instalar Nexus/Core, sem app Connector, e abrir/gerir cada runtime gerenciado qualificado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Core embutido em serve, sem daemon Connector, pareamento ou WSS local obrigatório.


### J05 — Servidor realmente remoto

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** A sem executáveis/providers/projetos; B/C com Connector/Core e harnesses.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Operações e streams funcionam; Server não faz realpath/spawn de B/C.


### J06 — Rede outbound

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Firewall de B/C nega conexões entrantes e permite WSS/HTTPS ao Server; testar também o processo/sandbox do harness.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Controle via Connector e MCP HTTP direto via harness funcionam com tráfego de saída; nenhuma porta MCP local exigida.


### J07 — Paths heterogêneos

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** A Linux, B Windows e C Unix; roots diferentes do mesmo e de outros repositórios.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Vínculos lógicos autorizados, validação física local e nenhuma fusão por path/Git.


### J08 — 100 mil agentes

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Sem providers, popular 100 mil identidades no Server e importar uma key em B.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Queries indexadas e escopadas; não listar tudo nem criar recursos por agente offline.


### J09 — Um daemon, várias identidades

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** B importa agentes A1/A2 que usam o mesmo binário Codex e um agente Pi.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sessões/credentials/lanes isoladas, sem daemon por agente ou prompt broadcast indevido.


### J10 — Dois Servers

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** B conecta dois Servers distintos e remove/revoga binding em apenas um.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Namespaces, processos, cofre e tickets do outro preservados.


### J11 — First-use/second-use

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Configurar por comando da tela e executar runtime start repetidamente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Setup agregado uma vez; depois sem JSON/argv/endpoint/profile/grant/chave manual recorrente.


### J12 — Daemon automático

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Connect e runtime start concorrentes com daemon parado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Uma instância; daemon ready não abre todos os harnesses descobertos.


### J13 — Terminal independente

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Fechar CLI de start, TUI/log follower e encerrar cliente MCP HTTP tools-only independente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Daemon e runtimes independentes continuam; fechar cliente HTTP não encerra supervisor nem outra sessão.


### J14 — Turno versus processo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Enviar trabalho, interrupt, novo turno e runtime stop.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Cancelamento preserva runtime quando suportado; stop encerra recursos próprios, não identidade/histórico.


### J15 — Shutdown/crash

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Stop daemon/serve; depois SIGKILL do supervisor em cenário controlado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Drain/containment e relatório real; sem kill alheio ou trabalho indefinido não declarado.


### J16 — MCP HTTP tools-only direto

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Usar conversa não gerenciada com MCP HTTP antes/depois de instalar e desligar Connector; também testar sem Connector instalado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Harness chama somente o Server; identidade preservada, nenhum proxy/subprocesso MCP e nenhuma adoção de conversa pelo runtime.


### J17 — Work bridge nativa não MCP

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Pi sem MCP HTTP recebe tarefa e chama contexto/claim/complete via extensão qualificada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesmo domínio canônico; nenhum servidor/proxy/envelope MCP no Core/Connector; texto livre não completa handoff.


### J18 — Consumo exclusivo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Uma entrega com MCP pull e dois runtimes disponíveis ao mesmo agente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um consumidor lógico; sem duplo turno/grant/resposta por multiplicidade de conexão.


### J19 — HITL concorrente

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Provider pede aprovação; CLI/UI respondem, agente tenta autoaprovar e decisão chega tarde.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Autoridade existente, CAS, geração/turno corretos; timeout/deny não aprovam.


### J20 — Recebido não é concluído

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Observar ACK WSS, aceitação nativa, fim de turno e handoff em cada adapter.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Estados separados, nenhum marco antecipa outro sem evidência.


### J21 — Resposta perdida

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Perder ACK após submit nativo possível, reconectar e repetir consulta/ID.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem replay automático; recibo/unknown/reconciliação pelo mesmo intent.


### J22 — Partição e revogação

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Revogar key com WSS online e depois testar partição prolongada/relógio alterado.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Online invalida derivados; offline limita por lease, sem prometer revogação instantânea.


### J23 — Gerações e takeover

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Canal antigo e novo/daemon clonado disputam mesma sessão.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Um owner, fencing/reconciliação; sem failover silencioso ou processo duplicado.


### J24 — Eventos/retention

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Interromper ACK, enviar duplicatas/out-of-order e ultrapassar retenção.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Ingressão durável idempotente e watermark contíguo; gap explícito, terminais não ocultos.


### J25 — Saturação

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Flood texto, disco cheio e consumidor lento enquanto chega interrupt.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Memória/journal/queues finitos, faixa crítica preservada e novas admissões bloqueadas quando necessário.


### J26 — Drift/config segura

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Trocar binary/root/symlink/home/hook e editar MCP existente durante setup.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Reprepare/approval/CAS; sem execução ampliada, JSON destruído ou secrets centrais.


### J27 — Quatro adapters

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Qualificar Codex/Pi/Claude managed e attach existente por versão/SO delimitados.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma implementação Core local/remota e capabilities comprovadas, sem sucesso simulado.


### J28 — Upgrade/rollback

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Migrar Nexus legado, atualizar Connector/Core com journal pendente e instalar wheels limpos.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Histórico/IDs/negações preservados, drain/reconcile e dependências acíclicas.


### J29 — Segredos/ameaças

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Inspecionar argv/log/config/export/metric; tentar handle/agent/server spoof e shell injection.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem chave canônica/admin de terceiros/provider secrets vazados ou efeito fora do escopo.


### J30 — Release coordenado

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Conferir resultados/SHAs/wheel hashes e gates provider/SO/multi-host em três relatórios.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Mesma evidência, bloqueios explícitos e nenhuma alegação de produto completo baseada só em fakes.


### J31 — Remoção MCP stdio

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Instalação limpa e upgrade do Nexus v0.2.0 com configuração MCP stdio; inspecionar entrypoints, módulos, exemplos e migração selecionada.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** MCP stdio ausente, sem shim/fallback; MCP HTTP direto mantém agente/key/histórico e outras entradas não são alteradas.


### J32 — MCP HTTP local nativo

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Somente Nexus/Core no host; abrir runtime gerenciado com MCP HTTP para o próprio Server.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sem Connector ou fachada; cliente chama endpoint HTTP de serve com capability válida e o Core só configura o cliente.


### J33 — Fronteira protocolo/transporte

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Exercitar stdio nativo dos adapters e inspecionar artefatos/portas de Connector/Core; testar harness com MCP apenas stdio.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Protocolos nativos funcionam; nenhum serviço/extra/CLI MCP/proxy; cliente incompatível recebe diagnóstico sem fallback stdio.


### J34 — Dois canais e autorização

**Estado:** NOT_RUN. **Camada:** `joint_multi_host`. **Tarefa:** NS16.05.

**Preparação:** Em runtime remoto com MCP HTTP direto, derrubar apenas WSS e depois apenas HTTP; expirar/revogar capability e manter outra conversa tools-only independente.

**Ação:** Executar o cenário original abaixo contra o código R4, preservando sua condição causal e qualificação.

**Resultado obrigatório:** Sessão gerenciada respeita lease/grants/revogação sem bypass, replay ou túnel; canal HTTP tools-only legítimo mantém política própria sem exigir daemon.


## Gates que não podem ser abreviados


G0: documento/artefato de desenvolvimento. G1: Server local real com Core, sem Connector; G2: Server e Connector reais em hosts separados e mesmo wheel; G3: escopo original por provider/SO e J-matrix. Candidato no catálogo não equivale a build qualificado. Fixture de Windows em Linux não equivale a teste Windows.

## Campanhas negativas transversais


Os casos TR4 devem manter as barreiras enquanto a asserção é feita: autorização vencida antes da escrita, lock/worker de dados bloqueado durante interrupt, journal bloqueado durante força, ACK2 ausente durante espera de lote2, callback antigo de attach após rotação, resposta HTTP perdida após commit e boot sem binário para história. Liberar barreira só no teardown. Contar bytes/chamadas/receipts no componente exercitado, não a presença de um método chamado guarded.