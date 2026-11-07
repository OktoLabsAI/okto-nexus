## 2026-11-07 — inicialização nativa isolada de DX-04

O ParticipantLaunch instalado iniciou o Codex 0.167.0 em perfil descartável,
com console próprio e chave Nexus sintética importada por stdin para um alvo
exclusivo do cofre Windows. A tela de login foi observada por rótulos fixos;
nenhuma entrada, credencial de provedor ou solicitação produtiva foi enviada.
Não foi observada autenticação MCP nativa. O único initialize HTTP 401 foi o
controle negativo sem bearer do próprio harness.

A tentativa 001 falhou antes de CreateProcess: o binding de CreateJobObject
não aceitou nome None. A correção exclusiva do harness passou no diagnóstico
benigno com CLI --help, TTY nos três streams e Job vazio ao terminar. A tentativa
002 iniciou o cliente, mas o watcher registrou PermissionError de causa não
demonstrada. O resultado original continua UNCONFIRMED. O Job foi encerrado à
força com código 125 e zero processos ativos; o listener do Server foi fechado
e o alvo próprio do cofre ficou ausente. O agregado cleanup_confirmed=false
é preservado, assim como a ausência dos pós-checks abortados no runner.

A conferência posterior confirmou os hashes dos inputs da tentativa 002. As
contagens finais canônicas foram lidas em modo somente leitura; não há baseline
retido para afirmar igualdade antes/depois. Esses fatos não substituem os
pós-checks ausentes nem promovem o resultado original.

DX-04 permanece IMPLEMENTED: startup, vault e controle negativo não comprovam
consumo da credencial pelo cliente. Não houve alteração de produto, inferência,
acesso à conta autenticada, registro de serviço nativo ou novo aceite de M1.
As propostas e perguntas pendentes de autorização/orçamento continuam válidas.
Evidência: `plans/agent_ops/evidence/r3-dx04-native-startup/milestone.md`.
