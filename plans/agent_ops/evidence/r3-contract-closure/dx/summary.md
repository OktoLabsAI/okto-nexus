# Reconciliação finita de cenários DX

Base Nexus: `4855abd56ae4733a3e0445d835a085a697dda1df`. Escopo exato: DX-T01…14, DX-T26 e DX-T28.

**Recomendação: 16 VERIFIED**, no escopo literal documentado. Nenhuma pendência concreta desses 16 predicados foi localizada. Nenhum status foi editado.

Os IN_PROGRESS carregam limites de campanhas mais amplas. A prova de init, edição transacional, CAS, proteção de credenciais nas superfícies selecionadas e honestidade dos diagnósticos não exige executar um provedor.

DX-T10: diagnóstico de ambiente FAIL/UNKNOWN é explícito e restrito ao contexto observado. A campanha real com variável ausente registrou Claude pending e Codex tools_error_present; não se inventa um diagnóstico textual Claude. Ela não passou por cofre real e não demonstra a cadeia completa cofre→launcher→cliente→cooperação.

DX-T08: interrupções são fault injection antes de escrita/backup/replacement e após replace, além de perda de checkpoint; não são queda de energia física.

DX-T09: a ausência de segredo é comprovada nas superfícies/arquivos/browser e homes explicitamente examinados; não declara cobertura de toda história Git nem de plugins arbitrários.

| ID | Razão específica |
|---|---|
|DX-T01|Init lê a identidade do Bearer e exige seleção existente; não há caminho de criação/rotação. Reconnect conserva setup/entrada/runtime e o guia seleciona identidade sem mutá-la.|
|DX-T02|Preparação participante exige identidade atual e não concede autoridade. Actor participante/revogado é recusado no bootstrap; snapshot canônico permanece idêntico.|
|DX-T03|O fixture já possui um binding managed antes de adicionar a entrada participante. Apply/reconnect deixam bindings, grants, execution policy e runtime overrides idênticos.|
|DX-T04|Plan deixa arquivo/vault intactos; apply usa entrada revisada e ownership, preservando outras entradas. Aprovação/hash ou configuração alterados são recusados antes dos efeitos.|
|DX-T05|CAS do documento rejeita plan stale; edição externa durante apply também é detectada antes do replace e seus bytes são preservados.|
|DX-T06|JSON/TOML preservam outros MCPs, modelo personalizado e posterior edição alheia; backup mantém bytes originais e remoção alcança só a entrada possuída.|
|DX-T07|Round-trip parametrizado Claude JSON/Codex TOML cobre caminho com espaços/Unicode, conteúdo Unicode e CRLF; JSON/TOML inválidos, chaves duplicadas, forma errada e UTF-8 inválido falham fechados.|
|DX-T08|Falha antes dos bytes de backup/replacement preserva o original; falha após replace mantém substituto íntegro e OUTCOME_UNKNOWN/possible_effect. Checkpoint perdido retoma por inspeção do mesmo efeito.|
|DX-T09|Config/exportação carrega referência de ambiente, não valor. CLI não recai em entrada com eco; erros HTTP/processo são sanitizados; processo filho recebe variável escopada, sem mutar pai. Guia/browser gera apenas comandos públicos.|
|DX-T10|Variável ausente/inválida produz FAIL no diagnóstico de ambiente; existência só prova o processo doctor e mantém client_reload/MCP UNKNOWN. Campanha com clientes reais registra ausência sem initialize autenticado, nunca como sucesso.|
|DX-T11|HTTP recusa redirect antes de seguir Location; somente a requisição inicial autorizada chega ao servidor. Alteração de contexto/configuração da origem falha antes de spawn.|
|DX-T12|Doctor padrão usa só metadados e recibos históricos: guards fazem falhar qualquer vault/HTTP/processo/recovery; arquivos e tabelas ficam idênticos. Modos ativos continuam flags explícitas.|
|DX-T13|MCP real TCP initialize/list_tools autenticado deixa tools_called=0 e participação/handoff/work UNKNOWN, sem abrir heartbeat de sessão agente ou alterar tabelas canônicas.|
|DX-T14|Sucesso técnico de setup não é cooperação. Mesmo texto NEXUS_CONNECTION_OK em reply legado/parent errado deixa participação UNKNOWN; prova exige recibo/proveniência e correlação canônica, não texto do modelo.|
|DX-T26|Finish managed continua atômico/idempotente. Falha tardia reverte identidade/chave/configuração; mudança concorrente de preset, identidade, grant ou endpoint retorna CONFLICT e conserva snapshot de grants/bindings/receipts.|
|DX-T28|JSON e exits são oráculos diretos: init/connect compartilham saída/checkpoints, doctor mantém shape/exits e usage/interrupt têm códigos separados. Invocações instaladas fora checkout confirmam JSON de falha sem efeitos.|

78 pares relatório/node PASS foram conferidos por parsing dos XMLs retidos. Nenhum teste novo, conta, serviço nativo ou inferência foi executado.

Cada entrada da matriz inclui literal/linha do plano, implementação com SHA, teste com assertions e oráculos de erro, node PASS/XML com SHA, limite e pendência específica (null). M1/M2/R3 e campanhas fora desse escopo permanecem abertos.
