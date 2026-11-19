# SI-031 — Abrir o Pi pelo connect do Connector

O Connector oferece o visualizador somente depois de confirmar a conexão Pi. A oferta padrão é recusável. `-i` solicita a abertura, e `--no-interactive` pula a oferta. O Nexus usa o login humano salvo, verifica o vínculo exato e seleciona a sessão pelo catálogo autorizado. O Connector valida que o recibo corresponde ao vínculo exato e à apresentação de leitura do Pi.

Em Windows ConPTY, o primeiro teste abriu o Pi, mas o Ctrl+C chegou também ao Connector e interrompeu a leitura do recibo. A correção trata o sinal no Connector durante a espera pelo visualizador Pi e restaura o tratamento anterior ao sair. O novo teste com os executáveis instalados retomou o setup, pulou a oferta, abriu o Pi existente, exibiu o resultado e devolveu o recibo `pi_remote_read` após o Ctrl+C. A abertura e a saída preservaram a mesma sessão e processo e não admitiram operações adicionais. [Resultados, revisões e hashes](si031-connector-pi-offer.json)

Passaram 97 testes do Connector e 20 do Nexus com os pacotes instalados. O ensaio nativo usou Pi 0.87.1 e uma resposta sintética local. O marco dispensa migração. O rollback reverte a oferta no Connector e restaura o pin anterior no Nexus. A qualificação de SI-031 ainda inclui o Claude e a comunicação entre máquinas.
