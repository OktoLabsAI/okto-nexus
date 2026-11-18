# Revisão dos runners — somente preparação

## Comandos de pacote

`package.command` agora usa `owned_commands.run_owned`, no Python host com psutil já disponível. Fecha stdin PIPE imediatamente, cria grupo de processo próprio e observa descendentes por PID/nascimento/executável. O prazo não mata apenas o wrapper RTK: tenta primeiro stop canônico quando identifica um Server foreground próprio por módulo, home contido no Temp e porta; depois oferece interrupção ao grupo próprio e 30 s de graça. Contenção final reconfere nascimento e executável de cada descendente observado, preservando dados. Processo remanescente, prazo excedido ou force impedem sucesso mesmo se o wrapper RTK retornar zero. São registrados processos conhecidos e listeners remanescentes; polling não é apresentado como enumeração de todos os filhos curtos. Não adiciona psutil ao prefixo congelado.

Esta alteração foi verificada somente por parse AST. Nenhum build/instalação/serviço foi iniciado para testá-la; gate SOURCE_ASSET_READY segue ausente e é avaliado antes de qualquer allocation.

`installed_regression.py` deriva do QC36 e não foi executado. Exige SOURCE_ASSET_READY e READY do pacote 0.3.7, SHA do wheel, prefixo congelado e contagem real de payload. Copia somente testes/helpers para outro Temp, sem `src`, sem modificar asserts ou argv de subprocessos dos testes. CWD e TMP são irmãos. O pytest filho roda no Python instalado `-I -B`, com stdin PIPE fechado e plugin que verifica origens de todos os módulos Nexus/Core/Connector carregados no início e no fim.

O ambiente usa allowlist e homes próprios. CODEX_HOME e CLAUDE_CONFIG_DIR apontam a caminhos próprios inexistentes, preservando a precondição de ausência de provider-home. PATH fica restrito ao Python instalado, sistema e Git. Não há fail-fast: inventário completo, fases e NOT_RUN ficam preservados, com faulthandler desligado e deadline externo. No deadline há CTRL_BREAK apenas no novo grupo próprio para permitir teardown canônico; depois de 30 s de graça, contenção exige PID+nascimento+imagem previamente observados na árvore própria. Dados são preservados. Timeout, contenção ou processo conhecido remanescente impede PASS. Amostragem de 250 ms não prova ter observado todos os filhos curtos.

A seleção proposta está em `installed-selection.json`. Só executar após os gates e confirmação do Root. O controlador usa psutil do host, sem instalá-lo no prefixo congelado.

## Live HTTP/MCP

`scripts/live_client.py` e CONTRIBUTING foram relidos integralmente. O script usa SDK HTTP real, duas identidades provisionadas canonicamente e dados sintéticos, sem harness/provider. Antes da execução no novo Python, sanitizar também o ambiente pai: bootstrap ocorre antes da criação do ambiente isolado do Server. Homes/TMP próprios, PATH vazio e comando `-I -B` fora do checkout.

Além do banner PASS e exit 0, a curação exigirá cleanup.physical_exit=true, saída física 0 e canonical_stop_exit_code=0 quando stop foi necessário. O script registra esse código sem assertá-lo; o banner sozinho não qualifica stop canônico. No deadline, preservar estado/logs, favorecer finally/stop canônico e conter somente árvore própria comprovada. Não foi executado nem alterado. SHA preparado: `c45643a809319861f21d73a3ddb2fc536b39f2e19e408563fd6cf907d26f2aa8`; drift exige nova leitura.

Twine cobre Nexus wheel/sdist novos e os dois wheels dependentes exatos; não se afirma docs integrais no sdist. READY será emitido apenas depois de build/install/smoke/audit/pip-check/Twine e drift 0.
