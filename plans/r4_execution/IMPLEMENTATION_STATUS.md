# Execução R4 — estado verificado em 2026-09-29

## Baseline

- Nexus: `feature/v0.2.0`, HEAD inicial `7ed52c22865a92c3768bc32508ed9e35dc5efdc3`, Python 3.13.1, Windows 11 10.0.26200, `uv.lock` existente.
- Core: HEAD inicial `1560d314ed2b478515dcbbe533436d7d0b027b09`, versão inicial `0.2.10.dev0`, NXL r3. Branch `feature/v0.2.0` criada.
- Connector: HEAD inicial `77fee6d8cde643d4310df5bbc5dfb643c496f677`, versão `0.4.0.dev0`. Branch `feature/v0.2.0` criada.
- O Nexus já tinha 599 exclusões rastreadas em `plans/`, três assets HTTP modificados e arquivos de planejamento R4 não rastreados antes desta implementação. Nenhum reset ou clean foi executado. O Core já tinha o arquivo não rastreado `=1`; ele não foi incluído em commits.

## Incrementos implementados

| ID | Estado | Evidência e limite |
|---|---|---|
| CORE-R4-02/03 | IN_PROGRESS | Core `0.2.11.dev0` gera e valida snapshot de inventário sem path, com revisão SHA-256/JCS completa e ref da instalação; 33 testes de Core passaram. NXL ainda é r3. |
| CORE-R4-02 | IN_PROGRESS | Core `0.2.12.dev0` expõe `discover_installations` sem runtime; o Nexus usa essa fachada para descoberta local. 27 testes direcionados de Core passaram, e `python -I` importou o wheel instalado. SHA-256 `bd5326357608906bdd80ccefc3db4890137d9e8dc00935a88c5f6dd955bf9d8e`. NXL ainda é r3. |
| CON-R4-05 | IN_PROGRESS | Preview do Connector usa a revisão do mesmo Core; função de publicação R4 usa o candidato completo. 18 testes CN4 e 1 novo teste passaram. Publicação HTTP autenticada ainda não foi implementada. |
| NS04.01/04.03 | IN_PROGRESS | Nexus consome catálogo e snapshot do Core sem criar runtime ou depender da aplicação Connector; dois testes locais e teste de protocolo passaram. Persistência e publicação por executor ainda pendentes. |
| NS01.04 | IN_PROGRESS | `GET /v1/connections/protocol` retorna objeto direto com header de revisão e indica NXL R4 indisponível. As demais rotas `/v1` ainda pendentes. 30 testes HTTP existentes passaram. |
| NS01.02/01.03 | IN_PROGRESS | Entrada principal agora é `adapters.inbound.cli.main`, sem ramo MCP stdio. Invocação sem comando mostra ajuda; flags antigas falham sem bootstrap. `serve` continua HTTP. 73 testes de CLI, retenção, tail e paridade passaram. Extra Core fixado, mas lock/instalação limpa ainda pendentes. |
| NS01.01 | IN_PROGRESS | `Deps`/bootstrap em `bootstrap.dependencies`, registro de tools/resources/instructions em `mcp.registration`; HTTP e CLI importam os módulos separados. Quatro testes de extração/paridade e 34 testes direcionados de HTTP passaram. |
| NS00.05 | IN_PROGRESS | Peer sintético com perda de resposta após commit e consulta do mesmo recibo; manifesto classifica provider e dois hosts como NOT_RUN. Cenário NS00.05 passou, mas peers de produto ainda pendentes. |
| NS02.01 | IN_PROGRESS | Chaves imutáveis por Server/executor/binding/sessão/stream/aprovação e geração tipada; teste de colisão entre namespaces passou. Writers persistentes ainda pendentes. |
| NS01.05 | IN_PROGRESS | Comando `admin migrate-mcp-entry` planeja uma entrada explicitamente escolhida, mostra diff sem chave, exige hash revisado para aplicar, cria backup e recusa edição concorrente. Cenário passou. Nenhuma configuração real do operador foi alterada; NS01.04 ainda incompleto. |
| NS02.02/02.03 | IN_PROGRESS | Migração 066 adiciona 20 extensões, FKs/índices, preserva endpoint negado e passa em banco legado; bootstrap mantém server_id/executor local estáveis sem claim. Registro remoto interno é idempotente e vinculado ao ator; rota autenticada e ticket bootstrap ainda pendentes. Três testes NS02 passaram. |
| NS04.01/04.03 | IN_PROGRESS | Catálogo e discovery local vêm do Core sem runtime; ingresso interno valida snapshot completo, escopo do produtor e sequência CAS, mantém duas publicações e não grava paths. Dois testes NS04 passaram. Rota com ticket e UI ainda pendentes. |
| NS02.04 | IN_PROGRESS | Binding lógico interno exige proposta APPLIED com digest do escopo e handle opaco do executor; não resolve path remoto. Repetição do mesmo vínculo preserva ID após expiração da proposta; raiz diferente exige outra aprovação. Validação efetiva da raiz no executor e rota autenticada ainda pendentes. |

O mesmo wheel local `nexus_connector_core-0.2.11.dev0-py3-none-any.whl` foi usado nos testes de consumidor Connector e Nexus: SHA-256 `41193bc203bb6425163b8992effb6dfa701d3ef309ed08832a58d84cc0c3158d`. Importação isolada com `python -I` passou. O artefato não foi publicado em PyPI; os extras `serve`/`serve-lite` do Nexus e a dependência do Connector fixam a versão, mas instalação nova exige disponibilizar esse wheel no índice/ambiente de instalação. O `uv.lock` do Nexus ainda não reflete essa dependência.

Substituição posterior: o wheel `0.2.12.dev0` de hash `bd5326357608906bdd80ccefc3db4890137d9e8dc00935a88c5f6dd955bf9d8e` foi copiado byte a byte para os três repositórios; os pins Nexus/Connector e `uv.lock` do Nexus foram atualizados. Os parágrafos anteriores registram o marco anterior, não o artefato corrente. O NXL segue R3.

`uv lock --check` e `uv sync --extra serve-lite --extra dev --frozen` passaram usando `vendor/wheels` do próprio Nexus. A suíte direcionada NS00/NS01/inventário passou 13 testes no ambiente sincronizado. O ADR em `docs/adr/0001-r4-authority-and-wire.md` registra responsabilidades, representação direta `/v1` e invariantes de efeitos; NS00.03/04 exercitam separação do envelope legado e rejeição R3/R4, inclusive receipt histórico R3. Nenhum desses resultados qualifica o dispatcher remoto.

O Core tem no commit `c67487e` um preview de codec NXL R4 em wheel `0.2.13.dev0`, mas `R4_BUNDLE_EXECUTABLE=False` e a revisão negociável continua R3. O Nexus/Connector ainda instalam `0.2.12.dev0`; não promover o preview a gate remoto. A suíte NS01/NS02/retenção passou 38 testes depois da migração 066.

Atualização: Nexus e Connector agora fixam e vendorizam o mesmo wheel Core `0.2.13.dev0`, SHA-256 `be0d974b036d6384e69655cff5556d6f5ee853f991a913087fe947c56fa2be96`. O `uv.lock` do Nexus aponta para esse wheel local; `uv lock --check`, `uv sync --extra serve-lite --extra dev --frozen` e 22 testes direcionados de Nexus passaram. O Connector passou oito testes de catálogo e inventário consumindo o wheel R4 parcial. A revisão negociável permanece R3 e `remote_execution_ready=false`; este marco não habilita efeito remoto.

Atualização seguinte: Core `0.2.14.dev0` (commit `c78daf5`, SHA-256 do wheel `759cdee946037ed5e215f901cdfb09b31baf350c7fde69e4d5f79bd41f515bee`) inclui payloads fechados de decisão/input, consulta e recibo com escopo de conexão e adapter IDs gerados do registry. Os 15 testes do codec passaram; importação `python -I` do wheel confirmou `development-partial` e `executable=False`. Nexus e Connector consumiram o mesmo wheel: 22 e oito testes direcionados passaram, respectivamente; `uv lock --check` e `uv sync --extra serve-lite --extra dev --frozen` passaram no Nexus. Ainda não há reducers nem qualificação de efeito remoto, portanto a revisão negociável permanece R3.

O wheel Nexus recompilado contém `066_execution_r4_expand.sql`; instalado em ambiente separado e iniciado com `python -I`, aplicou até a revisão 66 e persistiu os IDs de instalação. A validação foi feita em banco temporário, sem aplicar migração no banco do operador.

## Gates

G0, G1, G2 e G3 permanecem abertos. Nenhum teste acima prova provider real, efeito remoto ou multi-host. O endpoint de protocolo anuncia `nxl_accepted=[]` e `remote_execution_ready=false` enquanto o bundle R4 não existir. Não executar efeitos remotos com r3.

O pacote completo em `plans/` foi disponibilizado durante a execução. `python plans/validar_pacote.py` passou oito verificações documentais; `tests/execution_r4/test_ns00.py` passou os dois cenários de baseline e crosswalk. Essa validação não prova capacidade de produto. As demais tarefas seguem a especificação e nenhuma é marcada DONE por um recorte parcial.

Um wheel do Nexus foi instalado com o extra `serve-lite` num ambiente isolado com o wheel Core local; `python -I` importou ambos de `site-packages`, mostrou o help e serviu `/v1/connections/protocol` com `remote_execution_ready=false`. O teste não substitui a atualização do lock nem o bundle NXL R4.
