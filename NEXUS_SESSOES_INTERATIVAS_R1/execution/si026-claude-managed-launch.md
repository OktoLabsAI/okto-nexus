# SI-026 — Lançamento gerenciado da sucessora Claude

A composição pública do Core aceita a prova do host para uma conversa salva. A prova vincula o histórico, o escopo, as revisões e o perfil preparado. O lançador exige o mesmo diretório de estado e revalida o perfil antes da abertura e do envio. Após criar o processo, confirma o hook autenticado de retomada, o caminho exato do histórico e o registro do processo no Windows Job antes de aceitar entradas. [Referência do hook de abertura](https://code.claude.com/docs/en/hooks#sessionstart)

Com o Core instalado e o Claude Code 2.1.328 real, a composição pública abriu o histórico salvo e executou um turno na mesma conversa. O leitor se desconectou durante a execução. O turno continuou no mesmo processo e publicou apenas a resposta final, depois de um segundo hook ter prolongado o turno. Em outro perfil descartável, os hooks desativados impediram a confirmação. O Core encerrou o processo antes de devolver `FAILED` e a repetição recuperou o mesmo recibo. Os ensaios usaram um modelo simulado em loopback e ferramentas desabilitadas. [Dados, revisões e hashes](si026-claude-managed-launch.json)

Passaram 92 testes do Core, 83 do Connector e quatro do Nexus com os pacotes instalados. O marco dispensa migração. Para reverter, reverta os commits e restaure os wheels anteriores em conjunto.

SI-026 continua em andamento. O lançador exige Windows, o binário revisado, modo `plan` explícito e uma prova emitida pelo host. A prova dos ensaios veio de um perfil descartável. A admissão e a verificação da configuração efetiva no Nexus, as aprovações, o attach e os controles de turno ainda precisam de integração e qualificação.
