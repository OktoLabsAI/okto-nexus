# SAFE-RG: RG-01, RG-02 e RG-11

Snapshot Nexus `af056bb10d1c1a8602bbeb64a4be352918834a84`; plano R3 inalterado. Tudo foi preparado em Temp, sem editar checkout ou ledger.

**Resultado: 9 identidades qualificadas no pacote instalado atual — quatro novas e cinco reaproveitadas.** Não são nove testes novos nem soma dos reruns. Nexus 9b18…, Connector a8cf… e Core 5721…, MCP 1.30.0; imports ficaram na venv CI qualificada. Os XMLs iniciais permanecem separados.

| Cenário | Mapeamento exato | Resultado atual |
|---|---|---|
| RG-01 | O teste antigo tinha dois runtimes e um MCP, sem comprovar a população pedida. Novo teste usa dois atores MCP autenticados e um runtime no mesmo workspace; troca mensagens, publica a resposta nativa canônica, verifica referências e ausência de novas identidades. | 1 passou |
| RG-02 | A disputa antiga era DIRECT; as outras disputas inspecionadas eram somente entre runtimes. Novo teste cria BROADCAST real e compara MCP-primeiro, runtime-primeiro e corrida, verificando um claim/epoch/efeito e nenhuma cobrança do perdedor. | 3 passaram |
| RG-11 | Reaproveitados os quatro estados de exclusão push→MCP e o caso remoto HTTP/WSS. Mesma identidade, pull vazio, claim persistido, uma entrega/turno. Nenhum teste redundante novo. | 5 passaram |

O helper `verify_competition` tem assertions fortes, mas não possui invocação atual com `combined_winner` não nulo; não foi contado como evidência. Os resultados históricos reaproveitáveis e hashes estão em `mapping.json`.

## Correções de fixture e relatórios

- Candidato inicial: 3 passaram e 1 falhou. O claim MCP enviava `idempotency_key`, opção somente do claim gerenciado; rodada diagnóstica confirmou VALIDATION_ERROR. Remover essa opção tornou ambos os lados elegíveis. A rodada final passou 4/4.
- RG-11 inicial atual: quatro locais passaram; remoto concluiu as assertions funcionais, mas cleanup falhou por `service_generation` ausente. O helper liga componentes manualmente sem entrar em `run_forever`, que cria esse campo no fluxo público.
- `fixture.patch` adiciona apenas generation sintética 32-hex após as duas construções manuais, com valores distintos. Mantém `_shutdown` e suas assertions. A correção foi compartilhada com o reviewer de RG-04. O remoto passou após o ajuste intermediário e novamente nos bytes finais compartilhados.
- Ruff integral do novo arquivo passou. O lint global preexistente do helper antigo não é declarado limpo.

## Entrega

- `candidate.patch`: arquivo novo + correção mínima do helper.
- `new-tests.patch` e `fixture.patch`: partes separadas para revisão.
- `candidate/tests/execution_r4/`: bytes finais dos dois arquivos.
- `qualification-nodes.json`: seleção de nove casos para eventual integração final.
- `mapping.json`: assertions, localização/sha dos arquivos, resultados históricos, tentativas atuais e limites.
- `artifact-manifest.json`: allowlist pública com hashes. Não inclui homes, DBs, vaults ou bearers de fixture.

Os novos casos usam HTTP/MCP via ASGI real, SQLite e Core, com I/O nativo sintético. O caso remoto reaproveitado usa HTTP/WSS loopback real. Isso qualifica os contratos destes RG, não dois binários MCP reais, provedor, serviço nativo, M1/M2 ou aceite global R3.
