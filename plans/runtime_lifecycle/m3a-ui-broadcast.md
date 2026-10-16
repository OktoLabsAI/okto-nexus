# M3a — Broadcast real após funcionamento contínuo

2026-10-16, Windows nativo, interface do Nexus em `127.0.0.1:8202`.
Instância M3a Nexus/M1 Core descrita em `m3a-validation.md`; nenhuma
reinstalação ou reinicialização foi feita durante este teste.

Pela aba Agents, Pi, Claude e Codex estavam `Local · Online`; Pi mostrava
`4/5 available`. Pelo Meta-harness, foi enviado um único broadcast ao workspace
Techridy às 14:19:52 (America/Sao_Paulo), pedindo somente a resposta
`NEXUS_M3A_BROADCAST_20261016_OK`, sem ferramentas, arquivos ou novas tarefas.

Resultado observado na interface: uma mensagem de broadcast, **3 destinatários,
3/3 ACKs e três respostas**, uma de cada harness. Os três terminais foram
abertos pelo painel lateral de sessões e apresentaram `Turn completed`.

| Agente | Sessão | Harness ready | Turn started | Turn completed | Estado observado |
|---|---|---|---|---|---|
| Pi | `ses_ef20f3d559d56e1c1a8b92d9de8996d3` | 13:31:50 | 14:19:54 | 14:20:00 | CLOSED; 70 eventos |
| Claude | `ses_8c3fc262f603336840eaa2dff016cfd5` | 14:20:34 | 14:20:37 | 14:20:42 | READY; 17 eventos |
| Codex | `ses_41cf446cb4fff4f2c917d1987a629824` | 14:20:40 | 14:20:42 | 14:20:47 | READY; 36 eventos |

O Pi utilizou uma instância aquecida por aproximadamente 48 minutos. Claude e
Codex fizeram startup neste envio. As respostas chegaram sem intervenção manual.
Horários são os apresentados pelo terminal, com precisão de segundos; este
cenário isolado não substitui a distribuição de desempenho do M7.

Limitação observada: o terminal Codex registrou falha do MCP adicional
`okto-pulse` e timeout de startup de 30 s do `playwright`. O MCP do Nexus
apareceu pronto, e o turno terminou. Nenhuma configuração MCP foi alterada.
Este teste não qualifica esses servidores adicionais nem encerra o gate UI-C.

A captura da interface foi exibida na conversa. Não há arquivo de screenshot
persistido neste relatório. Nenhuma credencial ou configuração de MCP foi
copiada para a evidência versionada.

O gate UI-A completo permanece pendente: ainda depende de M2 integrado,
contenção e isolamento de falhas. O presente resultado complementa somente a
validação instalada de M3a e a disponibilidade observada na interface.
