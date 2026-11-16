# PR-00 — fixtures e baseline atual

Seis casos usam `migrated_factory`, `tmp_config`, `fake_clock`, repositórios SQLite e os serviços atuais Graph/OBS. Os dados ficam no diretório temporário do pytest. Não houve serviço, processo nativo de agente, provedor, browser, instalação de dependências ou alteração de produto.

As fixtures contêm duas workspaces; identidade global sem sessão; A→B→C sem mensagem do operador; A em duas sessões/workspaces; três tentativas distintas para um handoff; relatório OBS com TTL; identidade revogada; e sucesso de trabalho coexistindo com obrigação de cleanup pendente. As linhas de execução são entradas sintéticas do read model, não prova de execução real. O marcador de credencial de A é falso e necessário ao contrato de disponibilidade OBS; nenhum token é publicado.

`seed_scenario(..., agents=100, activities=1000, events=100000)` cria exatamente 100 agentes, 1.000 handoffs, quatro sessões, três tentativas e 100.001 eventos (100.000 sintéticos + um OBS). “Activities” aqui significa entradas de handoff, não a futura entidade unificada da Home. A página atual de eventos retorna dez registros e permite cursor sem sobreposição; o teste não carrega o histórico inteiro na UI.

## Validação e medidas

Comando reproduzível e pins em `qualification.json`. Resultado final: **6 testes únicos PASS**; Ruff F PASS. A rodada intermediária também teve os mesmos seis casos: não somar resultados. O antecedente de fixture OBS incompleta e o aviso final de assertion rewriting estão documentados em `antecedents.json`.

`baseline.json` deriva das propriedades do JUnit final (`qualified.xml`): 20 amostras locais, uma leitura de aquecimento descartada, mesma transação de leitura, `perf_counter`, p95 pelo nearest rank. A contagem de SQL e `total_changes` são observadas. A medida de encoding é JSON, **não renderização**.

| Leitura existente | Escala medida | p95 leitura | SQL/leitura | JSON |
|---|---|---:|---:|---:|
| Graph/application | 6 agentes, 6 handoffs | 1,142 ms | 10 | 3.357 bytes |
| Página de eventos | 100 agentes, 1.000 handoffs, 100.001 eventos; LIMIT 10 | 0,122 ms | 1 | 2.428 bytes |

Esses números excluem conexão/transação inicial, HTTP, rede, autenticação, browser e cold start. Não medem o Graph com 100 agentes nem a nova Home. Não comprovam seus alvos de 500 ms, 2 s ou payload inicial. O ambiente usa dependências do `.venv` existente, metadado instalado 0.3.3 e código editável do checkout; não é qualificação de wheel 0.3.4.

As fixtures oferecem entradas reutilizáveis para os próximos PRs. Ainda não testam a projeção Home, chave de atividade/deduplicação nova, authz HTTP da Home, painel lateral, feature flag, streaming, render/a11y ou rollout/rollback. Não promovem nenhum dos 73 casos de aceitação por inferência.
