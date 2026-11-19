# Renderer do Pi e RPC na mesma sessão

O ensaio usou o Pi 0.87.1 instalado, com Node 24.15.0. Um único `AgentSessionRuntime` executou o `runRpcMode` do Pi. O `InteractiveMode` recebeu esse mesmo `AgentSession` e escreveu a tela em um terminal de captura.

O RPC admitiu um turno e o provedor de teste do próprio Pi manteve a resposta em espera. O ensaio abriu o renderer, desanexou e reabriu enquanto o turno estava ativo. O RPC respondeu às três consultas com o mesmo ID de sessão e indicou que o turno continuava em execução. O segundo renderer mostrou o resultado. O RPC publicou um `agent_settled` e a mesma sessão gravou um único par de mensagem de usuário e resposta. O dono foi encerrado uma vez, após o EOF do canal RPC. [Dados e escopo do ensaio](si025-pi-shared-owner.json)

O renderer usado no ensaio tem acesso apenas à saída e omite três ganchos internos da versão examinada que tratam dos sinais do processo, das configurações globais e da vinculação de extensões. Assim, a vinculação dos handlers de extensão continuou com o RPC. O ensaio usou perfil e projeto isolados, o provedor sintético local do Pi e um terminal em memória. Ele cobre a continuidade do runtime durante o detach. A apresentação via Nexus, entrada, extensões reais, concorrência da fila e abertura em um terminal de operador ainda precisam de qualificação.

O ensaio foi repetido em duas execuções isoladas. Passaram também 30 regressões existentes do adaptador Pi no Core.

Para repetir, execute `python NEXUS_SESSOES_INTERATIVAS_R1/execution/si025-pi-observer-probe.py --node <node.exe> --pi-release <raiz-do-release>`. Use a raiz do release 0.87.1 que contém `node_modules`. O comando salva os dados em um diretório temporário e retorna o resumo e os hashes dos módulos examinados.

A etapa adiciona ensaio e evidências ao ledger. A reversão retira esses arquivos e referências, sem migração. A etapa seguinte verificou o mesmo processo sob a propriedade do `PiRpcConnector`. [Ensaio com o Core](si025-pi-core-owned-session.md)
