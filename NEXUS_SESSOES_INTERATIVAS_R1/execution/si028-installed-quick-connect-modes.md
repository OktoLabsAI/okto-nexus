# Quick Connect com Git nos dois modos de apresentação

No CLI instalado em Windows ConPTY, os planos com `-i` e `--no-interactive` mantiveram a mesma revisão e o mesmo perfil. Com Git real, o nome veio do remoto do repositório pai e a pasta filha de invocação permaneceu a raiz de execução. A configuração só foi aplicada depois da confirmação.

O ID ocupado abriu o mesmo seletor nos dois modos. Cancelar preservou o binding e o grant. Em outro projeto, a personalização do ID para `reviewer` manteve o nome derivado do Git e a raiz revisada, gerou uma nova intenção e exigiu uma nova aprovação. A revisão anterior foi recusada depois de substituída.

Depois de mudar o remoto Git, retomei o mesmo perfil nos dois modos. Os bytes do perfil, o nome, o ID e o binding permaneceram iguais. O SQLite confirmou duas configurações aprovadas e nenhum turno ou sessão. [Dados e hashes](si028-installed-quick-connect-modes.json)

Passaram a integração no terminal e 94 regressões instaladas. O ensaio usa Git, CLI e servidor reais e simula a verificação e o teste de conexão do harness. Os ajustes da fixture trataram os seletores de projeto e de ID como etapas interativas e removeram a dependência de espaços finais na captura do ConPTY.

O marco registra evidências, sem migração. O rollback consiste em reverter o commit de evidências.

## Revalidação no pacote instalado

No candidato `8bcee9bd`, oito invocações do executável confirmaram
as recusas esperadas para JSON interativo, entrada redirecionada,
flags conflitantes e abreviações inválidas. A escuta de teste
registrou zero conexões, e os caminhos de estado ficaram vazios.

O ensaio com Git e ConPTY repetiu os dois modos de apresentação.
Os planos mantiveram a mesma revisão. A personalização de ID exigiu
nova aprovação e invalidou a revisão anterior. Mudar o remoto Git e
alternar os modos preservou os bytes do perfil, o vínculo e o grant.
Passaram 115 casos da bateria de gramática e integração, mais os
ensaios de Git e modos em ConPTY. A qualificação usou respostas
de teste para a conexão e dispensa migração. O commit reverte o
registro da qualificação. [Resultados e hashes](si028-si029-current-connect.json)
