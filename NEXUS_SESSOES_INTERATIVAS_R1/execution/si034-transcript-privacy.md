# SI-T-H20 — Privacidade da conversa e dos resumos

O Nexus instalado abriu um processo Pi 0.87.1 no Windows. A ferramenta descartável retornou um caminho privado fictício e um valor sintético em um campo de credencial. A resposta colocou outro valor sintético em texto com formato de credencial. O histórico do processo confirmou os três valores antes da projeção. A ferramenta dispensou acesso a arquivos e rede. [Resultados, versões e hashes](si034-transcript-privacy.json)

- A leitura autorizada percorreu 28 páginas de um evento por vez. As atualizações coincidiram com as da API de gerenciamento. A conversa omitiu o conteúdo da ferramenta, mascarou a credencial na resposta e sinalizou o truncamento do texto em 4.096 bytes. O resultado canônico também omitiu os três valores.
- As listagens de sessões, o resumo por agente e a Home omitiram os valores e o caminho privado de lançamento. A chave de outro agente recebeu uma lista vazia e HTTP 404 ao pedir a conversa. Um workspace ou uma geração divergente também produziu HTTP 404. Os corpos de erro permaneceram sem os valores protegidos.
- O SSE autenticado publicou só a posição da conversa e seu escopo. Uma geração divergente foi recusada antes da abertura do stream. O fechamento canônico encerrou o Pi. O teste conferiu a integridade do SQLite, encerrou o listener e removeu a chave TLS temporária.

Passaram o ensaio instalado e 28 regressões de conversa, incluindo cursor, lacunas e histórico sem hidratação de artefatos. As primeiras rodadas corrigiram a rota do resumo por agente e a comparação do escopo SSE, que contém oito campos e omite as quatro revisões internas da API de sessão. A integração usa HTTPS e SSE em loopback. A evidência cobre a projeção do Nexus com dados sintéticos e a reversão do commit dispensa migração.
