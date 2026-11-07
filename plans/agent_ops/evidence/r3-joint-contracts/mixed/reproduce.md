# Reproduzir a proposta isolada

Não aplicar nem executar estes comandos automaticamente. A árvore pública é uma allowlist de evidências, não contém as homes privadas usadas nos testes.

1. Criar novo diretório Temp. Exportar somente `tests` e `plans/contratos` do commit Nexus `af056bb10d1c1a8602bbeb64a4be352918834a84` com `rtk proxy git archive --format=zip --output=<arquivo> <commit> tests plans/contratos`; extrair em `<Temp>/isolated`.
2. Aplicar `candidate.patch` nessa cópia (`rtk proxy git apply --check`, depois `git apply` apenas quando autorizado). Ele adiciona um teste e cinco linhas ao helper existente. As cópias finais em `candidate/` permitem conferir bytes.
3. Em `isolated/pytest.ini`, usar `[pytest]`, `asyncio_mode = auto` e `testpaths = tests`. Não apontar pythonpath ao checkout.
4. Usar ambiente novo com as wheels exatas e dependências resolvidas declaradas em `mapping.json`, ou a venv CI qualificada em modo somente leitura. Não modificar uma venv compartilhada. O runner exige `-I`, versões corretas, imports instalados e perfis descartáveis.
5. Executar `rtk proxy <python-qualificado> -I <Temp>/run_candidate.py <nome-inédito> <nodes>`; os nodes exatos estão em `qualification-nodes.json`. Cada tentativa escreve XML/qualification novos e nunca sobrescreve tentativa anterior.

Os comandos executados estão nos `reports/*/invocation.json`; a seleção nova produziu quatro casos e RG-11 mais cinco. Os erros iniciais e a correção da fixture estão mapeados. Não copiar DBs, WAL/SHM, vaults, perfis ou bearers para evidência pública; manter os limites sintéticos e não chamar isso de campanha de provedor/serviço nativo.
