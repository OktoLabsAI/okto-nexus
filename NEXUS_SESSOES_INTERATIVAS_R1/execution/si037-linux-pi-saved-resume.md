# SI-023 / SI-025 / SI-030 / SI-031 / SI-037 · Retomada salva do Pi no Connector Linux

O Nexus reconhece a identidade revisada do Pi 0.87.1 com Node 24.15.0 em Linux x64 para retomada no Connector que encerrou a origem. O fluxo exige fechamento comprovado, o vínculo e as credenciais aprovadas e um histórico local íntegro. O Connector reserva uma única sucessora. [Identidades e resultados](si037-linux-pi-saved-resume.json)

Com os wheels instalados no Ubuntu 24.04.5 em WSL2, o CLI usou o perfil já configurado. O ensaio recusou a retomada enquanto a origem estava ativa. Depois do fechamento canônico e da saída do Pi, cancelar a revisão deixou a contagem de operações intacta. Alterar o arquivo no ambiente temporário resultou em recusa sem admissão. Após restaurar os bytes, a confirmação no pseudoterminal abriu uma única sucessora no mesmo Connector.

A sucessora carregou o mesmo arquivo e a mesma folha do diálogo sem chamar o modelo. Repetir `session resume --json` devolveu os mesmos IDs de sucessora e operação. Uma segunda intenção foi recusada. O turno seguinte estendeu o histórico original uma vez e o fechamento canônico encerrou a sucessora. O caminho do arquivo ficou no host. O Pi real usou respostas simuladas em loopback.

O ensaio integrado e 196 regressões passaram, com 98 regressões em cada sistema. Na primeira tentativa, a abertura do turno entrou em reconciliação depois que o canal inicial mudou de geração. Na prova final, antes de criar trabalho, o daemon temporário voltou a se conectar com o vínculo já configurado. O ensaio final cobre a retomada sobre esse canal. O WSL de teste e seu disco foram removidos depois da coleta. [Hashes e dados do ensaio](si037-linux-pi-saved-resume.json)

O marco altera apenas o Nexus e dispensa migração. O rollback reverte o commit deste marco. A retomada com Pi incorporado ao Nexus em Linux, a prova em outra máquina, macOS, as campanhas com provedores e a aceitação humana permanecem abertas. O passo local seguinte é validar o fluxo incorporado em Linux.
