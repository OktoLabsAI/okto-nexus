# SI-017 e SI-036 · Avisos de fim de turno na conversa

Ao abrir uma conversa, a Home apresenta o histórico em silêncio. Conforme recebe o texto do harness, mantém o foco no controle ou trecho que a pessoa está usando. Quando um turno observado termina, a região de acessibilidade avisa uma vez. Se uma página trouxer vários fins de turno, mostra a contagem em um aviso. Os avisos seguem as páginas já verificadas da conversa, inclusive quando a pessoa ainda precisa carregar mais histórico.

O endpoint de conversa envia a posição e o desfecho do turno a partir do resultado canônico da mesma sessão e época. A consulta reutiliza a transação de leitura da página e inclui apenas eventos terminais daquele intervalo. O leitor omite repetições tardias, resultados antigos ao montar o painel e desfechos ainda sem projeção canônica. Os controles de sessão e o formato do histórico técnico continuam usando suas APIs atuais.

Passaram 421 testes do frontend, 36 testes Python no código-fonte, os mesmos 36 no pacote instalado em diretório temporário, o build da interface e o `twine check --strict` do wheel e do sdist. No Chromium real, o histórico foi aberto sem aviso e 24 fragmentos apareceram durante a leitura sem emitir avisos. Dois resultados de turnos distintos geraram dois avisos, e o terminal duplicado ficou silencioso. O foco permaneceu na conversa. A árvore de acessibilidade expôs a região `status` como educada e atômica.

O ensaio alimentou o pacote instalado com eventos sintéticos em uma cópia descartável do banco e usou a API real. Uma tentativa inicial usou uma sessão já fechada, que abre o histórico sem assiná-lo. A execução concluída usou uma sessão de leitura ao vivo no mesmo ambiente isolado. A leitura por software assistivo ainda precisa ser ouvida para concluir SI-T-E14. O aceite humano da experiência segue pendente.

O rollback é a reversão deste commit do Nexus. A mudança dispensa migração. [Dados e hashes](si017-grouped-turn-announcements.json)
