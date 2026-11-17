# Revisão final de aceite — proposta somente leitura

Revisão do plano consolidado (seções 1–14, backlog e aceites), prompt, ledger atual, `tools/reconcile_quick_connect_qualification.py`, fontes relacionadas e evidências QC12–39. Não executa suíte nem modifica ledger/Git. O Root comunicou o corte final `9bc4034663ca63cfee43790b4bc03c38f8bdebcc`; o artefato final ainda está em qualificação. As propostas **após o instalado passar** abaixo são condicionais, não resultados antecipados.

## Decisão proposta

É defensável encerrar a **implementação funcional** quando o novo pacote repetir os casos afetados de cancelamento e renderização, além dos novos testes persistidos. Não vi outra funcionalidade obrigatória ausente após as duas correções desta revisão. Isso não encerra a campanha real, a regressão ampla nem o aceite humano. A seção 14.3 exige separar esses gates; não propagar I09 a todas as tarefas que compartilham esse ID na matriz.

O ledger observado ainda registra 144 PASS / C02 NOT_RUN / G08 FAIL / I09 BLOCKED. Esse é um retrato anterior ao pacote final: não mudar G08 para PASS apenas porque QC35 derivado ou QC38 source passou. Se os novos nodes instalados confirmarem os mesmos asserts, C02 e G08 podem passar, preservando a falha a36 e os cortes derivados como antecedentes. A contagem resultante seria 146 PASS / 1 BLOCKED, **para os cenários e limites citados**, não “todos os gates verdes”.

## Requisitos

Proposta de `VERIFIED` por requisito significa o comportamento literal comprovado nas camadas citadas, após repetir as fronteiras alteradas no pacote final. Não significa provedor/OS universal. O gerador atual força os vinte requisitos a `PARTIAL`; esse laço deve ser substituído por decisões explícitas, sem importar automaticamente os juízos deste relatório.

| Requisito | Proposta após o instalado final | Base concreta / limite |
|---|---|---|
| R01 posicionais/legado | VERIFIED | Parser/dispatch QC12; três nodes legados originais repetidos em QC38 (source), a repetir instalado. |
| R02 aliases | VERIFIED | Allowlist e precedência exercitadas nos nodes parser/dispatch/CLI QC12; alias não executa outro CLI. |
| R03 CWD/path | VERIFIED | QC17 e QC27: override, raiz independente, CWD removido e junction alterada. QC28 prova física POSIX em WSL. |
| R04 projetos autorizados | VERIFIED | QC23 diretório completo/homônimos; QC34 C13 ancestral realmente registrado; QC35/C02 verifica sugestão e zero criação antes de consentir. |
| R05 Git/fallback | VERIFIED | QC12 Git + QC20 + QC32; fontes locais reais onde declarado, faults de reader explicitamente injetados. |
| R06 raiz não ampliada | VERIFIED | QC21 monorepo, QC34 C13, clones separados QC32; não inferir workspace por nome Git. |
| R07 picker seguro | VERIFIED | QC15 oito casos + política negada: escolha/cancelamento, stale/candidate exato, token hostil e normalização. Claude selecionado no dado incompleto encontra a cerca real de provider-home, não onboarding completo. |
| R08 ID manual/automático | VERIFIED | QC14 codex-2 e QC14b nova intenção codex-3; proposta não é ID bound. |
| R09 namespace | VERIFIED | QC03/QC24: dois bancos/Servers, projetos distintos, executor remoto autorizado; QC25 corrida real no reserve. Não equivale a dois computadores físicos. |
| R10 vocabulário | VERIFIED | QC18 output antes do chat e QC05/QC31 navegador em inglês; profile técnico preservado no JSON, retirado do comando básico por projeção estrutural. |
| R11 colisão/recovery | VERIFIED | QC16/QC19, retry da própria intenção, CAS F17, ocupado/pendente/desativado e seletores contraditórios. |
| R12 preservar contexto | VERIFIED no recorte | QC04 terminal, QC12 originais, QC25 preservação da primeira conexão, QC30 remoto e QC31 sessões exatas. A regressão ampla separada continua NOT_GREEN. |
| R13 revisão/cancelamento | VERIFIED condicionado | QC21 oito efeitos antes de `y`, QC18 hash novo; QC38 quick/legacy cancelam honestamente. Root corrigiu também cancel/EOF dentro de Personalizar, a repetir instalado. |
| R14 sucesso/ID | VERIFIED condicionado | Bound/full seven-reference invariants e output QC04/QC18; QC39 acrescenta retorno humano seguro e não o imprime como sucesso de plano/pendência. |
| R15 scripts/JSON | VERIFIED | Input proibido/PIPE, seleções não implícitas, plan sem serviço/Git/Test; QC38 e final confirmam cancel/reuse/JSON. |
| R16 reuso canônico | VERIFIED | Finish/receipt/reserva reais HTTP/SQLite; QC33 é Server foreground/PID/ServeLock/resolver real compartilhado, com Test/version sintéticos. |
| R17 remoto | VERIFIED | QC30 23 GET após associação, mesma tupla, zero mudanças em 12 tabelas e nenhum path de operador enviado ao Connector; remoto é visão do Server embedded, não duas máquinas. |
| R18 UI existente | VERIFIED no recorte | QC31 quinze checks, 86 GET/0 POST, um ID e duas sessões canônicas distintas/saídas exclusivas; sem menu novo, sem aceite humano ou sessão simultaneamente executando. |
| R19 legado | VERIFIED no recorte | Golden de omissão/hash, adoção metadata-only e preservação de extensões; nodes originais QC12/QC38. Sem migração em massa. |
| R20 comprovação/distinção | VERIFIED técnico; gate real BLOCKED | Há provas por camada e origens/payloads. Registrar explicitamente I09, broad NOT_GREEN e plataformas declaradas; não chamar isso de qualificação real completa. |

## Tarefas e etapas

| Tarefas | Proposta | Justificativa de aceite |
|---|---|---|
| QC-001 | manter VERIFIED | Baseline antes de editar, branch/delta/isolamento registrados; não depende de campanha final. |
| QC-002–003 | VERIFIED | Gramática/DTO/ADR e fixtures autoritativas, decisões de namespace e recuperação exercitadas. |
| QC-004–008 | VERIFIED | Normalização, aliases, inventário/política, JSON não interativo e vocabulário têm casos executados; QC15 complementa o bare literal. |
| QC-009–014 | VERIFIED | Root/provenance/Git/diretório/seleção/CAS: QC17/20/21/23/27/28/32/34 e concorrência QC25. C02 só ganha a promoção final com o caso instalado correto. |
| QC-015–020 | VERIFIED | Reserva/vínculo transacional, idempotência, adoção, tombstones/ocupação e decisões de colisão: QC03/04/07/14/16/19/24/25. Não se exige daemon físico para o nível unidade+SQLite/HTTP desses cenários. |
| QC-021–022 | IMPLEMENTED agora; VERIFIED condicionado | Fluxo/revisão completos; a correção nova de cancelamento, inclusive Personalizar, precisa do pacote final. Primeiro/segundo harness no mesmo projeto foram comprovados com peers inertes, não provedores reais. |
| QC-023–024 | IMPLEMENTED agora; VERIFIED condicionado | JSON bound/partial e sucesso já tinham prova; QC39 agora fecha o render por shell com contexto explícito. Não herdar o antigo PASS H09 só do echo sem shell. |
| QC-025 | VERIFIED no recorte | Disco local após commit repara somente atalho pela mesma intenção/receipt, sem replay; nova saída mantém pending técnico, não oferece comando básico substituto. |
| QC-026–028 | VERIFIED no recorte | UI/catalog tuple, multisessão, remoto/participant/Server antigo e legado têm provas executadas distintas. A lista de test_ids comum contendo I09 não transforma todas estas tarefas em campanhas reais. |
| QC-029 | IMPLEMENTED; VERIFIED para execução/rastreabilidade da matriz, após curadoria final | Pode verificar a tarefa de executar/registrar a matriz com I09 explicitamente BLOCKED; não usar esse status para afirmar que a suíte ampla está verde. |
| QC-030 | VERIFIED somente nos ambientes declarados | QC22 console Windows real Ctrl-C; QC37 counterpart real Enter/50→100 colunas/resume; QC27 quoting vetorial e QC39 shells reais; QC28 202 casos Linux WSL2 selecionados. Não representa todas as plataformas/terminais/versões Python. |
| QC-031 | BLOCKED | Campanha de provedor nova precisa de consentimento/budget próprios e resolução da guarda UNKNOWN. Nenhum teste sintético, console ou WSL a substitui. |
| QC-032 | IMPLEMENTED; VERIFIED documental após conferir pacote final | Guia registra syntax/segurança/rollback e agora suporte explícito de shell. Conferir os bytes do guia no sdist/wheel final; exemplos não afirmam campanha executada. |
| QC-033 | IMPLEMENTED/PARTIAL no encerramento | Build/isolamento/rollback podem passar, mas G6 deve relatar a dependência QC-031 BLOCKED e broad NOT_GREEN. Sem release/deploy automático. |

G0–G3 podem ser considerados verificados no escopo técnico. G4 aguarda os novos casos instalados de cancelamento/output; G5 tem prova de compatibilidade por camadas. G6 pode ser **decidido e relatado**, mas não aprovado como qualificação integral enquanto QC-031/broad estiverem abertos.

## Lacunas funcionais identificadas nesta auditoria

1. **H09:** o antigo `resume_argv`/QC27 provava só vetor e `shell=False`, sem render próprio. Corrigido em `quick_connect_render.py`/`quick_connect_outcome.py`; [QC39](qc39-shell-render/qualification.json) tem 37 focais source PASS e [shell-proof](qc39-shell-render/shell-proof.json) usa somente argv-echo inerte real: PowerShell 7.6.10 e WSL2 `sh`→`dash`, com aspas, apóstrofo, Unicode, vazio, `$()`, backticks, metacaracteres e marcadores ausentes. Windows PowerShell 5.1 recusa **antes** da invocação; cmd não é suportado. Isso fecha a implementação do requisito no suporte declarado, condicionado à repetição no pacote final.
2. **Cancelar dentro de Personalizar:** o ramo `restart is None` ainda retornava 0 com a revisão como último documento. Root corrigiu com o mesmo cancelamento honesto (variável `canonical_metadata`, não True literal), incluindo c/vazio/EOF; o novo pacote deve repetir esses casos. A correção não é prova retroativa de PASS do a36.

Não identifiquei outro componente funcional obrigatório faltando. Isso é uma conclusão de revisão limitada, não uma prova universal de ausência de defeitos. Não criar novo daemon/menu/setup nem alargar Core/Connector para “fechar” os gates restantes. Operações intencionalmente não implementadas — rename/rebind arbitrário, TTL automático de reserva incerta, roteamento MCP por ID, instalação/login de harness — não são pendências ocultas deste plano.

## Ajustes de rastreabilidade recomendados ao Root

- Somente após QC36/finais efetivamente passarem, atualizar o gerador `FINAL_CANCELLATION_QUALIFIED` e apontar C02/G08 ao novo pacote/nodes. Hoje o tool ainda reinstala o juízo FAIL do a36 e força todos os requisitos a PARTIAL; executar esse gerador sem revisão pode sobrescrever o retrato final.
- H09 deve apontar também QC39 e a prova instalada final, mantendo o antigo QC27 como antecedente vetorial; não afirmar que Windows PowerShell 5.1/cmd executam o comando exibido para PowerShell 7.3+.
- Preservar D25 como auditoria **dos sinks locais configurados e dados efetivamente observados**. QC34 final não é auditoria universal de telemetria ou todos os estados transitórios; a prova lock1byte tem identidade/owner/hash estritos. F20 verifica a revisão real antes de consentir, não substitui D25.
- `I08 PASS` é literal para wheel/sdist, entrada e dependências corretas. Acrescentar o pacote final sem apagar os dois relatórios QC09 broad; não converter a falha/hang/remainders/proveniência mista em PASS.
- Corrigir a nota histórica de “CLI130 não qualificado”: era verdadeira no transporte anterior, mas QC22 depois provou o sinal no console próprio. QC37 original recusado continua NOT_QUALIFIED; seu counterpart posterior prova somente o console declarado.
- Manter intactos os fracassos humanos UI-R1. QC05/QC31 e automação de shell não comprovam descoberta/compreensão por participante, AT/speech nem uma nova jornada humana. WSL não é CI Ubuntu nativo completo e console Windows não é toda implementação PTY.
- A formatação LF/persistência dos testes e um suite count verde não bastam: ligar os nodes finais aos asserts e preservar as fontes/hashes dos cortes antigos. QC38 é SOURCE_ONLY com 1.013 payloads PR27 de dependência intactos; não é o novo pacote Nexus.

Nenhum novo teste, provedor, sessão Windows, serviço ou prefixo foi iniciado para esta revisão. As únicas execuções adicionais de H09 estão delimitadas em QC39 e já foram comunicadas separadamente.

## Pins da leitura final

Observados em 2026-11-17T10:58:41.621686+00:00; ledger/tool podem receber a reconciliação posterior pelo Root.

- NEXUS_QUICK_CONNECT_R1/input/PLANO_CODEX_NEXUS_QUICK_CONNECT_CWD_ID_R1_CONSOLIDADO.md: 827e3a8bc8ba08a139d260026e81171dbc1843d0fd09fab5d488fd46af3a5f39.
- NEXUS_QUICK_CONNECT_R1/NEXUS_QUICK_CONNECT_LEDGER_R1.json: 653bad9c2088a31920a61c83416f616524bcc6c3b33e562a274f91c3e912c0c6.
- tools/reconcile_quick_connect_qualification.py: 88da568022b805bc9387bb63f35aa654b62fa4541132eb71513dd60e4c858645.
