## 2026-11-07 — observação da configuração reportada pelo Codex

O adaptador descartava campos de política e instruções presentes nas respostas
thread/start e thread/resume. O Core agora conserva oito campos limitados dessa
resposta e emite core/codex_thread_configuration como evento lifecycle da sessão,
antes de consumir a fila nativa. O journal recebe o evento já redigido e vinculado
ao server, executor, sessão e epoch. Não há nova chamada ao Codex, mudança de
política, conteúdo de instruções ou cópia do transcript.

Cada campo é reported, missing ou invalid. Valores ausentes não recebem defaults;
campos de política desconhecidos, valores excessivos e dados que exigem redação
não são apresentados como política completa. A observação inclui modelo,
provider, esforço, cwd, approval policy/reviewer, sandbox e caminhos de instruções.
O limite do payload é 48.000 bytes. Isso observa a resposta; não prova enforcement
do provedor, catálogo completo de ferramentas ou limite atômico de tokens.

Passaram 126 casos únicos do Core na fonte e no pacote instalado, incluindo
40 novos. As três falhas iniciais de fixture e sua correção foram preservadas.
Passaram também 7 casos instalados do Nexus e 26 do Connector, incluindo dois
novos testes de consumo: o evento é preservado em replay/transporte e não cria
resultado, aprovação, pedido nativo ou mensagem. Os 982 arquivos dos três pacotes
e os inputs dos testes permaneceram iguais; não houve imports do checkout.

Core enviado em `7f69d866f19616fcdd1ee83984f3806b1eb85ff5`, wheel `609e0fbbb20855c6b788d2523b0aeb6cdfbf4b3f5c9792c9e4a080284729c9dd`.
Os dois consumidores fixam esses mesmos bytes. Não houve chamada real ao provedor
ou ação de serviço nesta entrega; DX-T43 e M1 continuam pendentes de campanha real.
