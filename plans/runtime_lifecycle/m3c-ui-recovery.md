# M3c — recuperação real e reinício pela instalação global

Data: 2026-10-16. Operação dos testes pelo Chrome, interface do Nexus em
`http://127.0.0.1:8202`, Agents, Meta-harness e terminais. Os journals e logs
foram consultados somente para correlacionar a evidência da interface.

## Instalação e recuperação do incidente

Instaladas conjuntamente as wheels já qualificadas nos 266 testes do M3c:
Nexus 0.3.1 (`3a68909`), Core 0.0.12 (`7bab651`) e Connector 0.0.10
(`0db859c`, implementação da wheel inalterada desde M2e). A verificação de
bytes da instalação global conferiu 534 arquivos Nexus, 156 Core e 98 Connector;
os hashes são os de `m3c-results.json`.

Antes da atualização, foram preservados backups SQLite consistentes por banco
(241 bancos, não um snapshot atômico entre bancos), logs e diagnóstico L7.
O M2e permaneceu em shutdown pendente após Ctrl-C; foi necessário terminar
somente seu servidor PID 20896 e launcher 41572, verificados por identidade.
Nenhum journal foi apagado, nenhuma configuração foi recriada e nenhum comando
incerto foi reenviado.

No primeiro boot M3c, geração embedded 67, HTTP pronto às 20:45:06 UTC.
As três intenções de abertura do Pi sem birth record receberam
`CONTAINER_STOPPED` às 20:45:17–18, automaticamente. O Pi ficou READY às
20:45:35; Claude às 20:45:10 e Codex às 20:45:08. Nenhum botão de recuperação
ou confirmação manual foi usado.

## Resultados pela interface

| Cenário | Sessão | Resultado observado |
|---|---|---|
| Claude enquanto Pi estava Recovering, antes do rollout M3c | `ses_8fda90e76b98f69e0787123bc2bd55e8` | `NEXUS_M3C_ISOLATION_CLAUDE_OK`, resposta final e 1/1 ACK; baseline M2e |
| Pi após recuperação automática, M3c | `ses_ca46e73c86de94e2063f717d2db20c68` | `NEXUS_M3C_RECOVERED_PI_OK`, resposta final e 1/1 ACK; one-shot encerrado |
| Claude na instalação M3c | `ses_0a6f974a44145b5ecd8ff438de04b525` | `NEXUS_M3C_INSTALLED_CLAUDE_OK`, resposta final e 1/1 ACK; sessão persistente pronta |
| Pi após segundo boot M3c | `ses_fa7f1c0e1d6fab395496441fff047fe8` | `NEXUS_M3C_RESTART_PI_OK`, resposta final e 1/1 ACK; one-shot encerrado |

Pi: requisição às 20:46:09, harness pronto às 20:46:29, turno iniciado às
20:46:32 e concluído às 20:46:38 UTC. Claude: requisição às 20:47:22, pronto às
20:47:52, turno iniciado às 20:47:55 e concluído às 20:47:58 UTC.
São observações individuais sob a carga atual da máquina, não percentis de desempenho.

## Encerramento normal e retomada

Antes do segundo reinício, Agents mostrou 4/5 instâncias disponíveis do Pi,
alvo aquecido 4, máximo paralelo 5, zero em execução/fila. A sessão persistente
do Claude permanecia READY. Com as respostas já concluídas, Ctrl-C às
20:48:54.165 UTC encerrou o Nexus M3c normalmente em **6,46 segundos**,
sem término forçado.

Segundo boot: HTTP pronto às 20:49:15 UTC, geração 68. Codex READY às
20:49:16.653, Claude às 20:49:18.965 e Pi às 20:49:54.724 UTC, todos na primeira
tentativa e sem erro. A sessão persistente anterior foi reconciliada como
CLOSED, preservando seu histórico. O novo pedido ao Pi foi enviado pela UI
às 20:50:03 UTC e respondeu corretamente.
Seu harness ficou pronto às 20:50:28, turno iniciado às 20:50:30 e concluído
às 20:50:36 UTC.

## Evidências e limites

Artefatos locais, ignorados pelo Git, em `build/runtime-lifecycle-m3c-live/`:
`install.json`, `controlled-shutdown.json`, `after-restart.json`, logs de cada
boot e imagens `pi-recovered-terminal.jpg`, `claude-installed-terminal.jpg`,
`pi-restart-terminal.jpg`. Bancos e logs brutos permanecem privados.

L7 está validado para a recuperação real observada. O gatilho original do
CONFIG_ERROR continua sem subtipo preservado; não foi atribuído a timeout
como certeza. O novo caminho de recuperação no mesmo owner foi qualificado
pelos testes instalados com processos Windows descartáveis; não se provocou
uma falha artificial no harness de trabalho do usuário.

UI-A permanece parcial: Codex está limitado pela quota externa já registrada
em L5. Ainda faltam os demais critérios M2/M3. O tempo de recuperação do Pi
continua incluindo varredura histórica; recuperação incremental é pendência
M4, e o tooltip local “Last contact: never” continua em L6. O teste não
qualifica Connector em outra máquina nem conclui M5/M7/M8.
