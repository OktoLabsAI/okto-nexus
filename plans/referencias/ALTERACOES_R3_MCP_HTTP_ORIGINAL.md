# Revisão 3 — MCP exclusivamente HTTP direto

**Data:** 25/09/2026. **Origem:** correção explícita do usuário nesta conversa. **Estado:** documentos/backlogs atualizados; nenhum código alterado e nenhum teste de produto executado.

## Decisão

MCP somente HTTP no Nexus Server. Remover o MCP stdio incluído na v0.2.0, sem preservação de legado/shim. Connector e Core não hospedam, encaminham, encapsulam ou oferecem MCP, seja stdio ou HTTP. O harness capaz de consumir MCP HTTP acessa diretamente o endpoint do Server. A configuração desse cliente pode ser automática, mas não cria dependência do Connector no caminho das chamadas. Stdio usado nos protocolos nativos de runtime continua permitido.

## Aplicação nos três projetos

| Projeto | Alteração normativa | Tarefas/testes centrais |
|---|---|---|
| Server | Remover implementação/entrypoints/docs/stdin MCP; manter HTTP direto e migrar somente configuração selecionada, sem mudar agente/key. Emitir e validar capability HTTP de sessões locais/remotas. | N00.5, N02.4, N03.5, N07.1–N07.5, N08.3–N08.4; TN-08, TN-11, TN-26, TN-29 |
| Connector | Remover proposta de comando `mcp stdio`, pacote/serviço/fachada MCP e relay HTTP/WSS. Gerar apenas configuração HTTP direta no harness; daemon segue WSS/runtime. | C01.5, C02.4, C06.1–C06.5, C11.3; TC-24–TC-27 |
| Core | Não extrair MCP stdio nem criar helper/extra de fachada. Templates declarativos de cliente HTTP e adapters nativos compartilhados; manter extensão não MCP limitada onde necessária. | K00.4, K09.1–K09.5; TK-33–TK-34 |

IDs preexistentes foram preservados, mas descrições e critérios foram corrigidos. Para execução já iniciada pela r2, reconciliar cada tarefa alterada; um PASS antigo de fachada/stdin MCP não comprova aceite r3. Não apagar evidências nem descartar outras mudanças corretas; atualizar status/evidência no repositório real após inspeção.

## Contratos e segurança

O anexo comum agora especifica a topologia única (A.13.1), autorização de chamadas MCP diretas sem bypass da sessão, distinção entre ticket NXL e capability MCP e comportamento com WSS/HTTP particionados independentemente. Configuração de cliente não pode exigir um handle IPC para encaminhar cada chamada. O modo tools-only independente deve funcionar sem instalar/iniciar Connector; isso não altera a regra de que desligar o daemon encerra seus próprios runtimes gerenciados.

A bridge para um harness sem cliente MCP HTTP continua apenas quando nativa, estruturada, limitada e qualificada. Não é um proxy MCP com outro nome, não recebe envelopes/catálogos MCP e não substitui o caminho direto de um harness compatível. Client MCP apenas stdio é transporte incompatível, sem fallback.

## Aceite adicional

J31 testa remoção de MCP stdio e migração; J32 prova MCP HTTP local sem Connector; J33 separa protocolo nativo de stdio MCP e inspeciona ausência de superfície MCP no Connector/Core; J34 verifica dois canais, escopos e revogação sem proxy/bypass/replay. Total atualizado: 38 fases, 190 tarefas, 135 testes próprios e 34 conjuntos (169 cenários). Todos permanecem PENDING/NOT_RUN neste pacote de planejamento.

## Uso

Utilizar os três documentos r3 completos, o contrato r3 e os backlogs r3. O guia `00_INICIAR_NO_CODEX.md` mantém a ordem incremental e as dependências entre os projetos. A versão NXL de fio permanece v1 proposta; r3 é revisão normativa dos planos/contratos, não alegação de release de software. Não voltar ao texto de fachada/stdio da r2 como requisito de compatibilidade.
