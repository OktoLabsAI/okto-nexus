# M09 — autoridade de sessão nos handlers MCP

Incremento parcial de NS03.04, NS12.01 e NS12.02. Não encerra M02/M09 nem
G0–G3. A implementação continua exigindo o mesmo Core `0.2.28.dev0` já
publicado nos consumidores; Connector e Core não mudam neste incremento.

## Implementação

- O middleware HTTP reconhece a capability somente em `/mcp`, via bearer.
  Autenticação exige sessão READY, lease aplicada e vigente, grant, revisões,
  binding, realização e política atuais. Não aceita a audiência nativa.
- A identidade derivada não carrega o hash da chave canônica. A autenticação
  por `AgentKeyAuthService` continua separada para clientes tools-only.
- Cada chamada exige `tools/call` e o nome exato da ferramenta em `actions`.
  O primeiro é teto de protocolo; não autoriza todas as ferramentas.
- Os serviços MCP recebem um decorador do port de transação. A autoridade é
  conferida depois de BEGIN, inclusive após espera pelo lock, no mesmo UOW
  do efeito. Owners, serviços compartilhados e dependências mutáveis continuam
  compartilhados com a composição existente; o contexto é isolado por request.
- Callers gerenciados usam o `workspace_id` aprovado no argumento
  `project_root`. Não há resolução de paths remotos no filesystem do Server.
  Clientes com chave canônica mantêm a resolução de paths existente.
- Migração 081 vincula `(handoff_id, claim_epoch)` ao escopo completo da sessão
  na mesma transação do claim. Complete exige esse vínculo e mantém os guards
  de permissões, elegibilidade, geração, ownership e verificação do domínio.
  Não cria um motor de handoff, inbox ou sessão legada paralelo.
- `agent_whoami` informa `authentication_source=session_capability` e
  `session_scope`; as instruções MCP distinguem o bootstrap gerenciado.
  A revisão da superfície é 61, sem adicionar ferramentas.

## Superfície integrada neste checkpoint

| Ferramenta | Fronteira de domínio |
|---|---|
| `agent_whoami` | Perfil do sujeito autenticado e escopo da sessão |
| `handoff_list_available`, `handoff_get` | Workspace canônico e visibilidade/elegibilidade existentes |
| `handoff_claim` | Claim canônico e vínculo transacional ao escopo R4 |
| `handoff_complete` | Mesmo claim, sessão e geração; permissões e resultado governado |
| `event_get`, `event_cursor`, `event_wait` | Workspace e visibilidade canônicos; nova autorização em cada UOW |

Outras ferramentas recusam capabilities mesmo quando seu nome foi pedido
na emissão. Em particular, não há fallback para inbox global, administração,
abertura de outra sessão, emissão de credencial ou execução de outro runtime.
Isso é cobertura parcial a completar, não exclusão dos requisitos do plano.

## Testes e alcance

Os comandos, contagens, falhas iniciais, hashes e artefatos ficam em
[test_runs_20260930_mcp_capabilities.json](test_runs_20260930_mcp_capabilities.json).

| Campanha | Resultado | Limite |
|---|---|---|
| Nexus R4 | 159 passes | Antes da adição do teste de concorrência; este passou separadamente |
| Handlers MCP finais | 23 passes | Modo estrito configurado antes do bootstrap |
| Integração instalada | 165 passes | Três pacotes, 476 arquivos conferidos; 385 arquivos dos consumidores iguais às fontes |
| Modo estrito instalado | Um pass | Reexecução com a fixture estrita corrigida, mesmos bytes de pacote |
| Regressão de domínio/autenticação | 309 passes e duas falhas iniciais | Duas expectativas legadas corrigidas; o arquivo completo de 20 casos passou depois, também instalado |

As campanhas se sobrepõem. Não somar contagens nem apresentar o rerun de um
arquivo como reexecução verde dos 311 casos da regressão.

`test_mcp_session_capabilities.py` usa o app HTTP/MCP e os serviços canônicos.
Discovery/qualificação e READY são pré-condições sintéticas da fixture.
Handoffs preexistentes são preparados pelo repositório; claim/complete e
observação passam pelos handlers reais. Não é aceite de provider nem da
jornada completa de onboarding/launch do host.

Cobertura: autoridade reservada versus ativa, audiência, duas permissões por
tool, workspace/identidade/sessão cruzados, opções de novo runtime proibidas,
claim não pertencente à sessão, elegibilidade de domínio, revogação entre
autenticação e mutação, falha de persistência com rollback, isolamento de
requisições concorrentes e independência entre MCP HTTP e socket de controle.

A regressão identificou duas expectativas legadas de `test_agent_connections`:
upgrade limitado à migração 65 e transporte stdio removido normativamente.
O teste de upgrade agora percorre 65–81, preservando identidade, replay e FKs.
O teste de revogação usa o cliente HTTP persistente real e confirma negação
após desabilitar MCP, retomada após habilitar e ausência de novo provider.
Os resultados com falha são preservados, sem tratá-los como passes.

O wheel foi construído em staging novo e instalado em um venv novo. O runner
usa `python -I`, cwd externo e compara os arquivos dos três pacotes com os
wheels e as fontes dos consumidores. Os três assets UI previamente modificados
pelo usuário permanecem incluídos no wheel de teste e fora do commit: esse
artefato não representa aceite de UI nem um release limpo.

## Trabalho restante obrigatório

1. Integrar `/v1/runtime/native-actions` e o backend Pi aos mesmos casos de uso,
   com payloads tipados, IDs duráveis, replay e conflito sem repetir efeito.
2. Completar inbox limitado ao workspace, outras ferramentas exigidas e
   consumo exclusivo/causalidade entre os caminhos MCP e nativo. A chave global
   não pode servir como atalho para uma capability limitada.
3. Persistir intenção/material protegido e compor configuração/ambiente de
   produção nos hosts embedded e daemon; nenhum host foi promovido a READY.
4. Provar os cenários integrais NS12, incluindo concorrência MCP/Pi/local,
   idioma, providers, migração/restore e o conjunto final instalado.

O próximo incremento deve adotar esta autoridade de sessão no serviço de
ações nativas, preservando o mesmo claim canônico e o escopo persistido.
