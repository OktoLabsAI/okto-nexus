# SI-023 e SI-030 · Confirmação da retomada salva

`session resume` agora mostra a sessão de origem, o workspace e o host antes de pedir confirmação. A fila fica na origem e a abertura da sucessora ocorre sem prompt. Enter cancela. Uma sessão ainda ativa recebe o diagnóstico para usar a anexação ao vivo, quando disponível.

Uma nova abertura exige terminal interativo e confirmação, inclusive quando já existe uma revisão sem operação. Depois da admissão, o mesmo comando pode consultar o recibo em `--json`. Se a resposta à admissão se perder, o CLI informa que o efeito está incerto, mantém a identidade da operação e orienta a recuperar o recibo com o mesmo comando. O CLI valida a linhagem, o escopo, a ação e o hash antes de apresentar o recibo.

O ensaio usou o Nexus instalado, o Claude 2.1.328 em Windows ConPTY e um endpoint de modelo simulado em loopback. Verificou a recusa em JSON e em pipe, o cancelamento por Enter e uma única admissão após confirmação. Após a perda controlada da resposta, o CLI recuperou o mesmo recibo. A sucessora retomou o UUID nativo exato e reteve o contexto da sessão de origem. Um turno posterior iniciado pelo teste concluiu pela sucessora. O teste encerrou seus processos e verificou a integridade do SQLite.

Passaram 53 testes no código-fonte, 59 com os wheels instalados e o ensaio em ConPTY. Também passaram a verificação offline do lock, a validação do wheel e a checagem de dependências instaladas. [Resultados e hashes](si023-si030-saved-resume-confirmation.json)

A mudança dispensa migração. Em caso de regressão, reverta o commit do Nexus. A qualificação do Claude remoto, entre máquinas e com provedores reais continua pendente.
