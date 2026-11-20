# SI-026 · Abertura vazia e retomada canônica do Claude local

Uma abertura vazia e explícita do operador pode iniciar o Claude no terminal gerenciado pelo Core. A sessão usa o grant vigente e pede um UUID nativo novo. O Core verifica o hook de abertura, o processo contido e o registro desse UUID antes de confirmar a abertura. A rota exige o Claude Code 2.1.328 revisado no Windows, o recurso de sessão habilitado e um perfil `plan` compatível. A seleção vem da intenção já admitida pelo Nexus. Aberturas fora desse perfil seguem a seleção anterior.

O leitor acompanha a abertura e o processo canônicos. O término de um turno pode atualizar o comprovante de histórico sem invalidar a revisão usada pelo leitor. Quando o Core confirma o histórico do último turno e o encerramento da sessão de origem, o Nexus pode abrir uma sucessora com o mesmo UUID nativo e uma nova sessão Nexus. A retomada usa a operação existente de histórico salvo.

No ensaio com os wheels instalados, um operador local abriu a sessão pela API e recuperou o mesmo recibo ao repetir a admissão. O Claude iniciou sem prompt. Um leitor se desanexou enquanto o turno estava ativo e outro leu a resposta no mesmo processo. Após o fechamento comprovado, a sucessora abriu sem prompt em outro processo, preservou o UUID e levou o resultado do primeiro turno para a continuação. Os dois pedidos de modelo foram simulados em loopback. O ensaio confirmou o fechamento das duas sessões e a integridade do SQLite.

A primeira execução expôs a mudança indevida da revisão do leitor quando um resultado fornecia um novo comprovante. A repetição, com a revisão vinculada à abertura e ao dono, passou. A verificação de retomada continua exigindo o comprovante integral e o fechamento do processo de origem. [Resultados, testes e hashes](si026-claude-canonical-fresh-terminal.json)

A mudança dispensa migração e preserva os recibos e filas. Para reverter o marco, restaure o Nexus e os pins anteriores do Core no Nexus e no Connector em conjunto. O ensaio usou as APIs de operador e anexação com ConPTY no Windows e o modelo simulado. Apresentação remota do Claude, testes entre máquinas e campanhas com provedores reais seguem pendentes.
