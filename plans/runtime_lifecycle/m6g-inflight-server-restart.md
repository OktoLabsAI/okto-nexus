# M6g — reinício do Nexus com execução remota em andamento

Data: 2026-10-20 UTC. Checkpoint parcial do critério M6 de interrupção de controle; sem decisão de adoção do supervisor separado.

## Falha reproduzida

Usei Nexus 0.3.1 instalado em ambiente descartável, Core 0.0.12 e Connector 0.0.10 instalados das wheels aprovadas, daemon Windows em outro processo com named pipe e Pi 0.87.1 real. Pela UI do Meta-harness, solicitei ao agente `m6e-pi` uma escrita de marcador seguida de uma espera de 35 s. O Pi registrou `M6G_ONCE` uma vez no arquivo do workspace. Interrompi somente o Nexus enquanto o trabalho permanecia em andamento; o Connector continuou vivo.

Após o reinício do mesmo home, o Connector tentou renovar o ticket, mas o servidor recusou a substituição porque o ticket anterior continuava ligado ao socket do processo morto. A rota lançou `CONFLICT` sem tratamento, devolveu HTTP 500 sem `X-Nexus-Connections-Revision` e o Connector classificou falsamente o erro como `VERSION_INCOMPATIBLE`. Ele ficou em `RECOVERY_ATTENTION_REQUIRED` após cinco tentativas e continuou sem reconectar após a expiração do ticket. Esta é uma falha concreta de autoridade de transporte durável após restart, não uma mudança incompatível de versão.

## Correção e validação

Na abertura do servidor, uma transação descarta apenas os donos de socket remotos, marca suas lanes como desconectadas e remove as janelas curtas de resume; leases nativas e publicações não são apagadas. Um ticket expirado pode ser substituído explicitamente pela mesma intenção e escopo, com as revisões e a credencial atuais; tickets revogados e tickets ativos ligados a outro socket continuam protegidos. A rota retorna o conflito estruturado e o cabeçalho de revisão caso a substituição seja legitimamente recusada.

Os oito testes focados de fence de startup, política de tickets e resposta da rota passaram em código-fonte com Core/Connector instalados. Instalei uma wheel local da correção no mesmo ambiente descartável e reiniciei somente o Nexus. O Connector original reconectou automaticamente na tentativa 43 e voltou a `CONTROL_READY`/`CONNECTED`, sem reinício do daemon ou intervenção na configuração. A UI exibiu ACK 1/1 para a chamada e uma resposta Pi com `M6G_DONE`; o arquivo contém exatamente uma linha `M6G_ONCE`. A entrega foi marcada como lida uma vez.

Uma inspeção somente leitura correlacionou a mensagem `msg_dd2a7d…`, a entrega `del_533450…`, a operação de domínio `op_fff61a…` e a operação nativa terminal `op_1da43d…`. O outbox de domínio registrou uma tentativa e `NATIVE_ACCEPTED`; o dispatch nativo registrou `attempt_no=1`, estado `RESOLVED_TERMINAL` e revisão 2. Os receipts da mesma operação foram `SUBMITTED` (revisão 1, antes do restart) e `SUCCEEDED` (revisão 2, após a reconexão). A publicação `op_1da43d…` no Connector estava reconhecida e seu journal marcou a operação `SUCCEEDED`. Assim, o ACK da UI, a resposta e o efeito único no arquivo pertencem a uma única tentativa nativa observável. A qualificação de revogação, expiração de lease, fases de parada e upgrade/rollback permanece pendente, conforme o plano original.

Na validação ampliada inicial, o caso parametrizado de integração `lease_renewal` falhou com `SESSION_UNKNOWN` no Core ao fechar uma sessão sintética após a renovação. O mesmo caso passou isolado depois, usando a wheel Nexus corrigida e as mesmas wheels Core/Connector, em 33,14 s. Ele roda com lifespan HTTP desativado e não executa o novo fence de startup. A divergência observada é intermitente sob a carga do host; não a usei como prova de causalidade da correção. Além disso, os 14 casos instalados de negação de lease e contenção de trabalho remoto passaram em 182,04 s. Isso valida o comportamento local dessas fronteiras; não substitui o corte M6 com o daemon separado e lease expirada durante o mesmo trabalho real.

Na mesma instalação descartável, passaram 19 testes do Core para watcher de lease já expirada e leases R4, 65 testes do Connector para renovação, publicação pendente, shutdown e limpeza de donos, e dois testes de processo do named pipe, incluindo shutdown com autenticação incompleta. Esses testes cobrem as peças isoladas do corte de expiração/parada. Continuam faltando a combinação em processo separado de expiração/revogação e mudança de geração, a parada durante native open, e upgrade/rollback. A matriz completa instalada do Nexus foi disparada no commit de código `c7006e2`.

O Nexus descartável e o daemon de teste foram encerrados. A instalação global continua parada e inalterada.
