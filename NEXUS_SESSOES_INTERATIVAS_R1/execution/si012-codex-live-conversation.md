# SI-012, SI-017 e SI-036 · Fragmentos do Codex na conversa

No pacote anterior, o app-server Codex 0.157.0 registrou dois fragmentos na sessão, mas a API de conversa só devolveu a mensagem completa. Os fragmentos do evento bruto deixavam de carregar uma identidade utilizável após a sanitização.

O Core agora inclui um fragmento sanitizado e limitado, com identidade nativa validada. A sanitização retém bytes pendentes por item da resposta, inclusive quando outros eventos chegam entre dois fragmentos do mesmo item. A Home usa a mesma identidade para anexar os fragmentos e substituir o texto com a mensagem completa. Se um fragmento exceder o limite, o painel mantém o prefixo e indica o trecho indisponível até receber a mensagem completa.

No Edge 157 em Windows, a primeira parte apareceu com 95 caracteres e cresceu para 170 antes de o turno terminar. A mensagem completa chegou com 178 caracteres na mesma linha. Durante as três atualizações, a posição de leitura ficou em 100 px, o alinhamento da mensagem anterior permaneceu fixo e o histórico manteve o foco. Um único aviso permitiu ir até a resposta com Enter. A API confirmou duas atualizações parciais e uma substituição com a mesma identidade. O resultado canônico coincidiu com o do pacote anterior.

Passaram 418 testes do frontend, 112 no Core instalado, 45 no Connector instalado e 44 no Nexus instalado. O ensaio usou o app-server real com respostas sintéticas em loopback e perfil descartável. Esta evidência cobre a versão registrada do Codex e o Edge no Windows. Leitor de tela, outros sistemas e qualificação com provedor real continuam fora desse ensaio. A mudança dispensa migração. Para reverter, reverta juntos a projeção e o bundle do Nexus e os pins do Core no Nexus e no Connector.

[Registro de evidências e hashes](si012-codex-live-conversation.json)
