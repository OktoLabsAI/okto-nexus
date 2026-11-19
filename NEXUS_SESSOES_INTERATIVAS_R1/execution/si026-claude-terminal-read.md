# SI-021 e SI-026 — Aprovação de leitura no Claude gerenciado

O Claude pode pedir autorização para ler um arquivo do projeto. Attention abre a decisão canônica e apresenta o caminho relativo. O Core mantém o pedido ligado ao prompt ativo e verifica a identidade do arquivo e de seus diretórios antes de autorizar a leitura. Recusar responde ao mesmo pedido. Uma troca detectada na verificação de envio bloqueia a leitura, mesmo que a aprovação do operador tenha sido registrada.

Este caminho foi ensaiado com Claude Code 2.1.328 no Windows, em modo `plan` e com decisões do operador habilitadas. O perfil habilita `AskUserQuestion` e pede aprovação para `Read`, bloqueia leituras fora do projeto e desabilita ferramentas MCP. O perfil e o conjunto de ferramentas são verificados na origem e na retomada. [Hooks do Claude Code](https://code.claude.com/docs/en/hooks) · [Permissões do Claude Code](https://code.claude.com/docs/en/permissions)

Os ensaios usaram o executável real, projetos descartáveis e um provedor SSE simulado em loopback. O terminal retomado leu o arquivo quando autorizado e recebeu uma recusa sem conteúdo quando negado. Repetir a confirmação recuperou a mesma decisão. Com os pacotes instalados, substituir o arquivo após a revisão impediu a leitura. A origem stream-json também recebeu o conteúdo exato apenas depois da confirmação canônica. [Evidências e hashes](si026-claude-terminal-read.json)

Passaram 121 testes do Core, 83 do Connector, 13 do Nexus e os 417 testes Node. Passaram as checagens dos contratos, dos wheels, do lock e o build do painel. O build registrou o aviso de tamanho de bundle.

No navegador, os 14 testes do painel de decisões passaram. Os cenários de leitura abriram a aprovação pela campainha de Attention, exibiram o caminho relativo e registraram uma decisão por pedido. Essa verificação usou o painel instalado e pedidos nativos sintéticos. A automação foi atualizada para usar a sessão de operador e a navegação atuais.

O marco dispensa migração. Para reverter, reverta os três commits e restaure os wheels anteriores. SI-021 e SI-026 seguem em andamento. Ferramentas e perfis fora da combinação revisada exigem qualificação própria.
