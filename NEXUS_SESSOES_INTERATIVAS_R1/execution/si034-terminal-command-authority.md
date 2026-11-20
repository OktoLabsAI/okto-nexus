# SI-T-H19 — Autoridade dos comandos no terminal

O Nexus instalado abriu uma sessão Pi 0.87.1 no Windows. O ensaio usou um operador descartável, HTTPS e WSS em loopback e um provedor determinístico sem acesso externo. [Resultados, versões e hashes](si034-terminal-command-authority.json)

- Pela API do terminal, dois comandos fora do catálogo e uma opção extra de permissões receberam HTTP 422. A consulta autorizada de status da mesma sessão recebeu HTTP 200. Repeti-la com apenas a chave de agente recebeu HTTP 401.
- Três conexões WSS completaram a anexação com escrita antes de enviar as verificações. O gateway encerrou cada canal com código 4409 ao receber um tipo de solicitação fora do contrato, uma opção extra de permissões ou texto com prefixo reservado a comandos. Nenhuma tentativa enviou uma chamada ao RPC nativo ou gerou entrada, controle ou turno.
- Depois das recusas, o mesmo processo Pi executou um turno autorizado. O resultado apareceu no terminal em Windows ConPTY. Ctrl+C desanexou a leitura e o fechamento canônico encerrou o Pi. O SQLite confirmou três anexos com escrita e um com leitura, todos desanexados e sem hashes de tickets ou desafios. O listener foi encerrado e a chave TLS descartada.

Passaram o ensaio instalado e 104 regressões de terminal, apresentação e validação de requisições. O Starlette emitiu o aviso de depreciação já observado nos testes com `TestClient`. A qualificação cobre o gateway local para o Pi no Windows e a API tipada de comandos. Este marco atualiza evidências e ledger. A reversão do commit dispensa migração.
