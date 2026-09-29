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
| CON-R4-05 | IN_PROGRESS | Preview do Connector usa a revisão do mesmo Core; função de publicação R4 usa o candidato completo. 18 testes CN4 e 1 novo teste passaram. Publicação HTTP autenticada ainda não foi implementada. |
| NS04.01/04.03 | IN_PROGRESS | Nexus consome catálogo e snapshot do Core sem criar runtime ou depender da aplicação Connector; dois testes locais e teste de protocolo passaram. Persistência e publicação por executor ainda pendentes. |
| NS01.04 | IN_PROGRESS | `GET /v1/connections/protocol` retorna objeto direto com header de revisão e indica NXL R4 indisponível. As demais rotas `/v1` ainda pendentes. 30 testes HTTP existentes passaram. |

O mesmo wheel local `nexus_connector_core-0.2.11.dev0-py3-none-any.whl` foi usado nos testes de consumidor Connector e Nexus: SHA-256 `41193bc203bb6425163b8992effb6dfa701d3ef309ed08832a58d84cc0c3158d`. Importação isolada com `python -I` passou. O artefato não foi publicado em PyPI; os extras `serve`/`serve-lite` do Nexus e a dependência do Connector fixam a versão, mas instalação nova exige disponibilizar esse wheel no índice/ambiente de instalação. O `uv.lock` do Nexus ainda não reflete essa dependência.

## Gates

G0, G1, G2 e G3 permanecem abertos. Nenhum teste acima prova provider real, efeito remoto ou multi-host. O endpoint de protocolo anuncia `nxl_accepted=[]` e `remote_execution_ready=false` enquanto o bundle R4 não existir. Não executar efeitos remotos com r3.

O pacote atual em `plans/` não contém `BACKLOG_R4.json`, `07_RASTREABILIDADE_R3.md`, `08_FONTES_BASELINE_E_DECISOES.md`, `contratos/` nem `validar_pacote.py`, embora `00_ENTREGAR_AO_AGENTE.md` e `VALIDACAO_DO_PACOTE.json` os citem. Portanto a validação documental anterior não é reproduzível neste workspace e o crosswalk completo de NS00.02 não pode ser marcado DONE. As tarefas independentes seguem a especificação textual disponível; nenhuma tarefa integral foi marcada DONE por um recorte parcial.
