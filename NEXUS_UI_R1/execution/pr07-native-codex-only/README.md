# UI042 / M3: derivado restrito a Codex A/B

Preparação técnica derivada da resposta explícita do usuário ao item
`call_7b291505d2a349ddb591321ccaefe5f7`, item0: executar apenas Codex;
múltiplas instâncias Codex permitidas. A referência recebida do agente raiz está
em `authorization-source.json`. Este diretório não altera nem reutiliza o
consentimento do candidato anterior `3ea51229…`; seus arquivos permanecem intactos.
Antes da execução, o agente raiz fará auditoria técnica deste candidato e emitirá
o arquivo de consentimento vinculado à resposta real. Não é necessária outra
pergunta ao usuário para esta restrição de escopo.

São duas conexões independentes Codex A/B, dois agentes e duas sessões exatas no
mesmo workspace canônico. Ambos usam exclusivamente `codex_app_server` e
`gpt-5.3-codex`, pelo mesmo executável/hash selecionado passivamente no candidato
anterior. O modelo precisa ser aceito pelo catálogo/configuração canônicos; não
há fallback de modelo, conta ou executável. Claude não é lançado, autenticado ou
selecionado. O parser puro de uso ainda retém testes legados de outro formato;
isto não concede permissão de execução desse formato.

A ordem máxima é A.setupTest, B.setupTest, A.work, A.continue, B.work, B.continue:
seis admissões Nexus, incluindo os dois Tests de setup. Cada continuação usa a
mesma tupla canônica, epoch e identidade nativa da sessão do trabalho anterior.
O segundo setup recebe o workspace_id devolvido pelo primeiro Finish. A revisão
e Finish permanecem canônicos. O snapshot de A usa GET setup e revisão canônica
somente leitura de grants, com ID estável, sem salvar autorização no checkpoint,
sem emitir grant ou reiniciar a conexão. A conexão e concessões de A são
comparadas após B. Duas instâncias da mesma instalação não alegam diversidade
entre provedores nem qualificação de Claude.

O trabalho útil soma um CSV de quatro despesas e devolve JSON exato; a
continuação verifica o total e calcula 10% de acréscimo, com oráculo local. Não
há reparação por pedido adicional. O prompt pede ausência de ferramentas, rede
e subagentes; isso não constitui um limite nativo garantido. Cada admissão pode
causar mais de uma requisição faturável interna ao CLI/provedor.

O limite permanece **500.000 tokens observados cumulativos**, gatilho preventivo
**450.000**, reserva **50.000**. Toda admissão reserva permanentemente **75.000**,
incluindo setup; a provisão nunca é liberada, mesmo após terminal. O débito é
`sum(max(75.000, observado_por_admissao))`; a próxima reserva deve caber em450k.
O gatilho ativo considera observado>=450k ou débito>450k. Se uma admissão exceder
75k, as seis podem não caber. Uso desconhecido, regressão, mudança de epoch ou
perda de correlação bloqueiam outra admissão; não se repete o pedido.

O uso Codex é o delta observado do contador cumulativo **por journal/sessão
exatos**, com baseline distinto por admissão e sem compensação entre A e B.
Uma amostra antiga não cobre uma operação nova: exige uso válido correlacionado
à operação/turno e evidência terminal dessa operação. `reported_accounting_final`
continua falso: o contrato app-server não garante contador final no mesmo evento
terminal. Provisão não é limite superior real de consumo; uso atrasado, retries
internos e ausência de cap nativo podem ultrapassar os valores. Isto não é um
limite de faturamento atômico ou garantia financeira.

Cada campanha usa UUID/root/porta/IDs novos, diretórios privados próprios e os
artefatos BXP já qualificados no venv temporário próprio. Não instala pacote
pessoal, não copia credenciais, não lê arquivos de autenticação/configuração do
provedor na preparação. Apenas após a autorização validada o CLI poderá usar a
conta já autenticada no provider_home declarado. O próprio CLI pode escrever
naturalmente nesse home; não se promete ausência de alterações pelo CLI.
Variáveis pessoais de produto/provedor são removidas da herança do Server com
comparação case-insensitive; DB/métricas e home do Nexus são explícitos próprios.

O Server é foreground, sem login trigger, serviço Windows ou reinício de sessão.
Após seis admissões, há janela passiva de até180s para outro agente observar a
Home/sessões/resultados reais no próprio Server. `public/observer-ready.json`
publica origem e IDs próprios, sem token de provedor. Somente
`public/observer.done` com campaign_id exato pode terminar cedo. Ausência registra
NOT_RUN, sem novo turno/replay. A navegação usará autenticação local canônica do
home temporário. Falha anterior leva diretamente ao cleanup.

Cleanup reconfirma instância/PID/geração/handle antes da parada normal; se preciso,
permite parada forçada canônica apenas desse Server próprio, conforme escopo já
autorizado. Não exige nova pergunta por PID. Só registra complete após saída
física, worker encerrado e recibo DRAINED da mesma geração. Dados ficam preservados.
Não apaga arquivos do usuário nem altera grants/leases para fabricar settlement.

Correção exclusiva neste derivado: o path de journal Work agora coincide com
`EmbeddedRuntimeHost._journal_path`, `core-runtime/session-<hash>.db`. O candidato
anterior usava uma pasta inexistente. O teste offline compara diretamente com o
método instalado, sem criar runtime. Setup continua em connection-tests/*/journal.db.

Validação: testes offline sintéticos e smoke real zero-admission com roots
inertes/provider_home vazio qualificam gates/orçamento/cleanup. Não demonstram
disponibilidade da conta/modelo, sucesso de inferência nem M3 real. A execução
real só ocorre após auditoria do agente raiz e consentimento genuíno vinculado
ao SHA deste candidato; a preparação não o executa.

Comandos (Python e SHA exatos no candidato/manifesto):

```
rtk proxy <own-python> -I driver.py dry-run --plan candidate-final.json --expected-plan-sha256 <SHA>
rtk proxy <own-python> -I driver.py execute --plan candidate-final.json --expected-plan-sha256 <SHA> --consent <genuine-consent.json>
```
