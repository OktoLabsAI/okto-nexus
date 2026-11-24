# SI-023 / SI-025 / SI-030 / SI-037 · Retomada salva do Pi incorporado em Linux

O executor incorporado do Nexus usa a identidade revisada do Pi 0.87.1 com Node 24.15.0 em Linux x64 para capturar o histórico antes do fechamento e verificar a prova depois da saída do processo. A sucessora passa pelas verificações já existentes de vínculo, perfil, geração, arquivo e ramo. [Identidades e resultados](si037-linux-pi-embedded-resume.json)

O ensaio instalou os wheels no Ubuntu 24.04.5 em WSL2. O processo Pi era real e as respostas eram simuladas. A autenticação do operador e as credenciais temporárias de ferramentas passaram pelo Secret Service numa sessão D-Bus descartável. O CLI instalado usou o ID público do harness, o workspace e a sessão exatos. O primeiro ensaio parou antes de iniciar o Pi porque o ambiente ainda estava sem Secret Service. A prova final usou o cofre protegido e rede limitada a loopback.

- Com o arquivo íntegro, o CLI recusou a origem ativa e deixou a contagem de operações intacta ao cancelar. Depois da saída do Pi e da confirmação em pseudoterminal, a sucessora reabriu o mesmo ID nativo e o mesmo arquivo sem chamar o modelo. O novo turno estendeu o ramo uma vez.
- Com o arquivo alterado após a verificação, a abertura registrou `PROFILE_DRIFT` antes de iniciar outro Pi. Repetir o comando devolveu o recibo dessa recusa. No caso íntegro, a mesma consulta recuperou o recibo e o ID da sucessora. Uma segunda intenção independente foi recusada nos dois casos.

Passaram os dois ensaios integrados e 162 regressões com os pacotes instalados. As regressões cobrem CLI, migração da tabela privada, verificação de histórico Pi e aposentadoria Codex. O WSL de teste e seu disco foram removidos depois da coleta.

O marco dispensa migração e pode ser revertido pelo commit do Nexus. Permanecem abertas a prova em outro host, a qualificação em macOS, as campanhas com provedores e a aceitação humana. O próximo ensaio local é qualificar o envio literal no Pi em Linux.
