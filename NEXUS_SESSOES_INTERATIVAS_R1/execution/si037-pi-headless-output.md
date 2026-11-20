# SI-T-H14 — Saída volumosa do Pi sem visualizador

O Nexus, o Connector e o Core foram instalados a partir dos wheels em diretórios temporários. No Windows, o Pi 0.87.1 rodou como processo nativo. A fixture admitiu dois turnos por HTTP na mesma sessão, com zero visualizadores conectados. As duas respostas vieram de um provedor determinístico local. [Resultados, versões e hashes](si037-pi-headless-output.json)

Durante o primeiro turno, o runtime drenou uma linha de 20 MiB de diagnóstico pelo stderr enquanto recebia deltas de resposta pelo stdout. O fragmento máximo do stderr foi de 4.096 caracteres. O trecho retido descartou a marca inicial e preservou a final. O Nexus publicou o resultado com o prefixo exato de 1 MiB da resposta nativa de 1.090.040 bytes e registrou `output_truncated = 1`. Os dois turnos terminaram com sucesso no mesmo processo.

Depois da conclusão, o CLI instalado abriu a mesma sessão em Windows ConPTY por WSS e exibiu o fim das duas respostas a partir do histórico nativo. Ctrl+C desanexou o visualizador e restaurou os modos do console. O encerramento canônico fechou a sessão e terminou o processo Pi. O SQLite registrou uma abertura, dois envios e um fechamento, com integridade confirmada. O listener foi encerrado e a chave TLS temporária removida.

Passaram o ensaio instalado de ponta a ponta e 15 regressões direcionadas de enquadramento, limites, renderização e resultados. A fixture precisou aceitar o valor numérico de truncamento e configurar uma janela suficiente para o modelo sintético, pois a compactação automática consumiu uma resposta programada na rodada anterior. Uma suíte suplementar com vários adaptadores reportou uma falha e parou na desmontagem do `TestClient`. O executor temporário foi encerrado após confirmação da espera na pilha. A qualificação cobre esse volume, no Windows em loopback, com as versões registradas.

O guia do terminal documenta a drenagem e o limite do resultado. O commit altera apenas documentação e evidências. A reversão do commit dispensa migração.
