# Renderer na sessão aberta pela CLI do Pi

O ensaio no Windows executou o `main` da CLI distribuída com Pi 0.87.1 e Node 24.15.0. Um hook de resolução temporário interceptou somente a importação dos modos pelo `main`, registrou o `AgentSessionRuntime` entregue a `runRpcMode` e repassou esse mesmo objeto ao RPC original. O hook foi removido antes de a CLI iniciar a sessão. O ensaio exige que a importação revisada ocorra exatamente uma vez.

O Pi aplicou o modelo e o perfil de teste, reconheceu a credencial sintética, ativou apenas a ferramenta `read` e carregou a skill e a extensão do perfil. Com `--no-approve`, manteve a configuração do perfil e recusou a extensão do projeto. As mesmas verificações passaram depois de fechar e reabrir o renderer. O provedor sintético recebeu um prompt, o resultado apareceu no segundo renderer e a mesma sessão registrou `agent_settled`. O ensaio observou zero tentativas de rede.

Com os wheels do Nexus e do Core instalados em diretórios temporários, a concessão R4 manteve o mesmo processo e o mesmo ID de sessão durante os dois anexos. Repetir a operação durante o detach devolveu o recibo original. A operação de fechamento terminou o processo e a leitura posterior foi recusada. A mesma prova passou com o código-fonte. O modo anterior de inicialização pelo SDK também passou diretamente e sob o Core. [Resultados e hashes](si025-pi-cli-owner.json)

Para reproduzir, use `python NEXUS_SESSOES_INTERATIVAS_R1/execution/si025-pi-observer-probe.py --node <node.exe> --pi-release <raiz-do-release> --cli-owner --core`. O modo `--core` precisa do Nexus 0.3.8 e do pin Core 0.0.16 registrados na evidência. O roteiro cria o perfil e o projeto descartáveis e restringe a leitura aos arquivos do ensaio e do release. Usa `--no-context-files` porque a busca de arquivos de contexto do Pi sobe aos diretórios ancestrais.

A etapa qualifica o ponto de integração no CLI modular do Pi. A rotina padrão do Connector seleciona outro entrypoint, o bundle. O renderer do ensaio escreve em um terminal de captura e a credencial é fictícia. A SI-025 segue em andamento. O próximo passo é vincular esse ponto de integração a um launch revisado do Core e ao canal autenticado do Nexus. A reversão retira o modo de ensaio e suas evidências. A etapa não exige migração nem muda a inicialização padrão do produto.

O script histórico é o de `f1003fc9e844d31858c4d1b90159b5e60f2700e1`. A versão atual do script reutiliza o launcher empacotado. [Abertura hospedada pelo Core](si025-pi-hosted-core.md)
