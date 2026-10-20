# M6g — reinício do Nexus com execução remota em andamento

Data: 2026-10-20 UTC. Checkpoint parcial do critério M6 de interrupção de controle; sem decisão de adoção do supervisor separado.

## Falha reproduzida

Usei Nexus 0.3.1 instalado em ambiente descartável, Core 0.0.12 e Connector 0.0.10 instalados das wheels aprovadas, daemon Windows em outro processo com named pipe e Pi 0.87.1 real. Pela UI do Meta-harness, solicitei ao agente `m6e-pi` uma escrita de marcador seguida de uma espera de 35 s. O Pi registrou `M6G_ONCE` uma vez no arquivo do workspace. Interrompi somente o Nexus enquanto o trabalho permanecia em andamento; o Connector continuou vivo.

Após o reinício do mesmo home, o Connector tentou renovar o ticket, mas o servidor recusou a substituição porque o ticket anterior continuava ligado ao socket do processo morto. A rota lançou `CONFLICT` sem tratamento, devolveu HTTP 500 sem `X-Nexus-Connections-Revision` e o Connector classificou falsamente o erro como `VERSION_INCOMPATIBLE`. Ele ficou em `RECOVERY_ATTENTION_REQUIRED` após cinco tentativas e continuou sem reconectar após a expiração do ticket. Esta é uma falha concreta de autoridade de transporte durável após restart, não uma mudança incompatível de versão.

## Correção e validação

Na abertura do servidor, uma transação descarta apenas os donos de socket remotos, marca suas lanes como desconectadas e remove as janelas curtas de resume; leases nativas e publicações não são apagadas. Um ticket expirado pode ser substituído explicitamente pela mesma intenção e escopo, com as revisões e a credencial atuais; tickets revogados e tickets ativos ligados a outro socket continuam protegidos. A rota retorna o conflito estruturado e o cabeçalho de revisão caso a substituição seja legitimamente recusada.

Os testes de fence de startup, política de tickets e resposta da rota passaram em código-fonte com Core/Connector instalados. Instalei uma wheel local da correção no mesmo ambiente descartável e reiniciei somente o Nexus. O Connector original reconectou automaticamente na tentativa 43 e voltou a `CONTROL_READY`/`CONNECTED`, sem reinício do daemon ou intervenção na configuração. A UI exibiu ACK 1/1 para a chamada e uma resposta Pi com `M6G_DONE`; o arquivo contém exatamente uma linha `M6G_ONCE`. A entrega foi marcada como lida uma vez. Não foi possível correlacionar esse resultado com uma identidade única de receipt nativa nas duas bases; por isso a prova exata de receipt/effect do critério M6 continua pendente, apesar da observação de efeito único e de uma resposta única.

O caso parametrizado de integração `lease_renewal` falhou durante a verificação ampliada com `SESSION_UNKNOWN` no Core ao fechar uma sessão sintética, após a renovação. O caso roda com lifespan HTTP desativado e não executa o novo fence de startup. Permanece uma falha de validação a classificar separadamente; não foi usada para declarar aprovação desta campanha.

O Nexus descartável e o daemon de teste foram encerrados. A instalação global continua parada e inalterada.
