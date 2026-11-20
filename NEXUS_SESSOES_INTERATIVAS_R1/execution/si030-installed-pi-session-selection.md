# Seleção de sessão Pi pelo CLI instalado

Na versão anterior, `connect -i` recuperou o binding local e listou duas sessões Pi vivas. Depois da escolha, recusou abrir o visualizador por falta de login humano, embora já existisse um login salvo para aquela instância.

Ao solicitar o visualizador local, o Nexus agora procura um login humano salvo para a origem e a identidade do Server já confirmadas. Só consulta o cofre se encontrar um único perfil para esse escopo. Revalida a origem e o Server antes de ler o token e confirma a sessão humana na API. Se houver vários perfis válidos para o mesmo escopo, a seleção do login é explícita em `session attach --operator-profile`.

O wheel corrigido abriu a sessão mais antiga de duas sessões Pi 0.87.1 com processos distintos. O CLI confirmou a configuração antes de exibir o seletor de `connect -i`. Abriu a mesma sessão com `session attach --id … --session-id …` e também pelo seletor de `session attach` sem o ID da sessão. A chamada JSON sem ID da sessão devolveu `SESSION_SELECTION_REQUIRED` e os dois IDs disponíveis.

Em Windows ConPTY, cada visualizador exibiu o resultado já registrado na sessão escolhida. Ctrl+C devolveu o shell e gravou o detach. Os dois processos e o binding permaneceram os mesmos durante os anexos. O SQLite confirmou três anexos na sessão escolhida e nenhuma operação, grant, teste de conexão ou envio adicional. As duas sessões foram fechadas canonicamente no fim do ensaio. [Dados e hashes](si030-installed-pi-session-selection.json)

Passaram 46 regressões instaladas e a repetição dos seis modos de conexão do marco anterior. O ensaio usou dois processos Pi reais e uma resposta de preparação determinística, com rede externa bloqueada. A primeira captura interrompia o cliente logo após a criação do anexo, antes de aparecer o resultado no terminal. A rodada conclusiva esperou o resultado em cada visualizador antes de enviar Ctrl+C.

O escopo cobre anexação local a uma sessão viva. A abertura de uma sessão nova com autorização própria, as campanhas com provedores e a qualificação entre hosts continuam no ledger. O marco dispensa migração. Para reverter, reverta o commit e restaure o wheel anterior.
