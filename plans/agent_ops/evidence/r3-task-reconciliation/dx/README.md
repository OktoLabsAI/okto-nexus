# Auditoria DX — leitura de rastreabilidade

`matrix.md` apresenta os 21 IDs originais com requisito literal, implementação/reuso, fonte exata, testes e XMLs PASS, qualificação pendente e recomendação por ID. `matrix.json` acrescenta SHA das fontes/evidências, linhas e expressões das assertions e oráculos de exceção esperada selecionados, subscopes herdados ainda não verificados e referências a falhas históricas.

Não houve execução de testes/campanhas, provider, cliente, serviço ou acesso a credenciais. Nenhum checkout, ledger ou evidência existente foi alterado. A normalização de mojibake feita pelo root durante a auditoria foi absorvida na leitura final; o texto normativo continua vindo do plano fixo, não de uma paráfrase do ledger.

As recomendações são por requisito literal. Onde a implementação e evidência correspondente bastam para um contrato puro, a matriz recomenda VERIFIED sem transferir para ele uma exigência de trabalho produtivo que pertence a outro ID. Onde o texto/campanha exige cliente ou harness efetivo, recomenda IMPLEMENTED e preserva NOT_RUN para o que não foi executado. Nenhuma recomendação fecha AC01, full R3, M1/M2 ou a cadeia real de credenciais automaticamente.

Nuance obrigatória: parsing de Claude/Codex, initialize autenticado com ambiente sintético, teste de processo filho e armazenamento/remoção de vault Windows são provas distintas. Não há, nas evidências consultadas, uma campanha única cofre real → launcher distribuído → cliente real → cooperação canônica. DX-02 actual_client_credential_resolution amplo permanece NOT_RUN.

As marcações genéricas antigas de renovação remota não representam produto ausente: o milestone de renovação/rotação tem XMLs instalados posteriores. O mesmo vale para init/launcher, bootstrap remoto de identidade/workspace e snippets de onboarding já substituídos. A matriz distingue essa reconciliação de novas implementações.

`pending-scenarios.json` conserva os cenários DX ainda não VERIFIED e mapeia relações temáticas com provas parciais da matriz. DX-T27, DX-T34 e DX-T39 continuam NOT_RUN. Esse mapeamento não recomenda promoção dos cenários. Registra também a dependência SVC-07 informada pelo root: falta expor a decisão explícita de força após timeout de drain; a contenção automática Core não substitui essa decisão. A implementação SVC-07 não foi reavaliada neste escopo DX.

`input-manifest.json` vincula a revisão aos heads e bytes consultados. XML PASS significa teste passado na campanha citada; não é uma nova execução sobre o checkout atual. As fontes atuais foram lidas separadamente, e nenhum relatório falho foi sobrescrito ou promovido. As assertions selecionadas são exemplos concretos de fronteiras correspondentes, não alegação de cobertura exaustiva de todos os caminhos do programa.

`index.py` e `build_matrix.py` são auxiliares somente leitura de AST/XML para montar este relatório, não um novo framework de testes. Os índices de trabalho completos ficaram no Temp pai; a allowlist inclui só a matriz, decisões, scripts e hashes de entrada pertinentes. Nenhum banco, home de fixture ou arquivo de credencial é incluído.
