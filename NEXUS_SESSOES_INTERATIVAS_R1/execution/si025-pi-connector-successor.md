# SI-025 — Retomada salva do Pi pelo Connector

O operador confirma a retomada pelo comando `session resume`. O Nexus confere a origem encerrada, o vínculo, o build revisado e o recibo de liberação. O Connector consulta o arquivo local e reserva a origem de forma durável para uma única sucessora.

O Core confere o perfil aprovado e a prova do arquivo, abre o caminho exato pelo argumento nativo `--session` e compara o ramo carregado em memória com o ramo da origem antes de publicar a abertura. Os caminhos e o conteúdo do arquivo ficam no host. O mesmo comando permite recuperar o recibo da admissão original.

O ensaio final com os pacotes instalados abriu o Pi 0.87.1 real em um novo processo no mesmo Windows. A origem já havia saído, e a abertura preservou o mesmo ramo sem chamar o modelo. O turno seguinte estendeu o arquivo original uma vez. O mesmo comando recuperou o recibo e uma segunda intenção de sucessora foi recusada. O fechamento final encerrou o processo.

No primeiro ensaio, o histórico intacto chegou à admissão e o Connector recusou a abertura antes de reservar a origem. A comparação incluía a concessão temporária de ferramentas da sessão anterior. A correção permite uma nova concessão no mesmo vínculo e mantém a conferência das credenciais aprovadas. No ensaio separado com esse primeiro candidato, uma alteração do histórico foi recusada antes da admissão.

A retomada integrada ao host local do Nexus e a validação entre máquinas seguem no ledger. Os ensaios usaram respostas sintéticas com a rede do Pi desabilitada.

A etapa acrescenta uma tabela privada de concessões no SQLite do Connector, na revisão 6. O rollback reverte os commits e pins dos três repositórios em conjunto. [Resultados e hashes](si025-pi-connector-successor.json)
