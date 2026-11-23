# SI-025 — Prova do histórico salvo do Pi

O Core consulta o processo Pi gerenciado após o fim do turno, com a fila nativa vazia e sem compactação, repetição ou comando de shell em andamento. A resposta privada identifica o arquivo, o último registro do ramo e o hash calculado na memória do mesmo processo. O Core confere esse hash com o arquivo dentro do perfil e do workspace aprovados. A leitura pertence à sessão, ao processo e ao lease exatos.

O Connector confere o arquivo novamente após a saída do processo e grava a prova junto aos recibos da origem e ao fechamento confirmado. A prova fica no SQLite do Connector, na revisão 6. A mudança é aditiva. O rollback usa os commits e pins anteriores em conjunto.

O ensaio com Pi 0.87.1 real e perfil temporário recusou sessão vazia, turno ativo e edição do arquivo que preservava o mesmo ramo. A reabertura de teste pelo argumento nativo `--session <arquivo exato>` recuperou o mesmo ID, o mesmo ramo e o diálogo original. O ensaio inicial expôs uma diferença de precisão do timestamp do Windows entre o caminho e o descritor aberto. A correção compara a estabilidade de cada leitura e passou no ensaio repetido.

Os dois ensaios finais por loopback passaram com os pacotes instalados. O Connector reteve a prova da origem intacta após a saída do daemon e descartou a prova do arquivo alterado entre a saída do Pi e a gravação. Ambos fecharam com `SUCCEEDED`. Os eventos e recibos do Nexus ficaram sem os caminhos privados. A regressão de resposta tardia também confirmou que caminho e hash ficam no host. As primeiras tentativas do ensaio do Connector expiraram porque o fixture esperava um estágio intermediário de recibo. A repetição aguardou o evento de início do turno.

A abertura pelo CLI do Nexus ainda depende da confirmação do operador e da concessão exclusiva de uma sucessora. [Resultados e hashes](si025-pi-saved-retirement.json)
