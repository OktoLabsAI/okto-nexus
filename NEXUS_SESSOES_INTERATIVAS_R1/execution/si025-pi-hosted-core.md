# Abertura hospedada do Pi pelo Core

O Core expõe `pi_hosted_rpc` como opção explícita para hosts confiáveis. Para o Pi 0.87.1 em Windows x64, a abertura exige o Node 24.15.0 revisado e o par de arquivos da instalação selecionada. O Core preserva a verificação já existente da instalação, do diretório de trabalho e da concessão. O launcher empacotado confere os hashes dos pontos de entrada antes de executar o `main` oficial do Pi com os argumentos autorizados pelo Core.

O launcher recebe da CLI o `AgentSessionRuntime` que seguirá para o RPC original. A confirmação interna usa o pipe de protocolo. O adaptador exige a confirmação da sessão exata e uma resposta `get_state` correlacionada antes de devolver o recibo. Um peer que só responde `get_state` é recusado no modo hospedado. A confirmação é interna ao processo e ao adaptador. Ela não concede acesso ao visualizador.

O ensaio `--hosted-core` cria a sessão pela composição real do Core, sem injetar uma fábrica de adaptadores. Usa um projeto e perfil descartáveis, uma chave fictícia, modo offline e um preload de teste para bloquear rede e desativar leitura de arquivos de contexto dos diretórios ancestrais. O ensaio verifica a posse R4, a leitura da sessão exata e o encerramento pelo recibo canônico, sem enviar um turno. O ensaio `--cli-owner --core` importa o mesmo launcher empacotado e acrescenta o renderer em memória e o provedor sintético. Assim verifica o detach e o resultado com a CLI carregando as configurações e extensões do perfil de teste. [Resultados e hashes](si025-pi-hosted-core.json)

As duas provas passaram com código-fonte e com os wheels instalados. Também passaram 41 testes do Core, 103 do Connector e 22 do Nexus com os artefatos instalados. Os dois pins contêm o mesmo wheel do Core e o manifesto de CI confere com os arquivos.

Para reproduzir, execute `python NEXUS_SESSOES_INTERATIVAS_R1/execution/si025-pi-observer-probe.py --node <node.exe> --pi-release <raiz-do-release> --hosted-core`, com o Nexus 0.3.8 e o Core 0.0.16 da evidência disponíveis no interpretador. Use `--cli-owner --core` no lugar de `--hosted-core` para o ensaio com o renderer.

A etapa dispensa migração. A reversão coordenada dos commits restaura os pins anteriores. A SI-025 segue em andamento e a opção de abertura continua restrita à composição confiável. Falta ligar a sessão hospedada ao canal autenticado do Nexus e validar entrada, fila, aprovações e detach em terminal real.

O script histórico é o de `90b5ca931436a99b70c5ea21fcb78c336e63af1f`. A versão atual também valida a conexão ao renderer privado. [Canal privado do Pi](si025-pi-private-renderer.md)
