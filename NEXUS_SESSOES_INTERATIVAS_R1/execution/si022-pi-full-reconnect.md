# SI-022 e SI-023 — Reconexão completa com Pi no Windows

O ensaio usou os wheels do Nexus, do Connector e do Core com Pi 0.87.1 e um editor em ConPTY. Um corte no WebSocket de controle do projeto temporário recusou novas conexões até expirar a prova de retomada. O HTTP de recibos continuou disponível. O provedor do Pi foi substituído por uma fixture determinística e o processo nativo ficou sem acesso externo à rede. [Pacotes e artefatos do ensaio](si022-pi-full-reconnect.json)

O turno original terminou durante a queda. A fila manteve a entrada original sem operação vinculada, e o editor voltou ao shell com o modo do console restaurado. Depois que a concessão expirou e o processo antigo saiu, o Connector abriu um canal em nova geração. A reconciliação encerrou a sessão antiga e a consulta do recibo devolveu `BLOCKED_SESSION`, com o mesmo identificador e sequência. O histórico nativo continha apenas o prompt inicial, e o recibo final do turno permaneceu `SUCCEEDED` na operação original.

Um segundo ensaio repetiu a queda e, depois de confirmar o recibo original, solicitou trabalho explicitamente em nova sessão. O novo turno usou outro processo e terminou com sucesso. Os históricos nativos registraram um prompt distinto em cada sessão, e a entrada bloqueada permaneceu na sessão encerrada. O encerramento explícito da nova sessão também produziu recibo `SUCCEEDED`.

Passaram 28 regressões no Nexus instalado e 41 no Connector instalado. A execução usou a mesma máquina para os dois hosts lógicos e não interrompeu a rede do sistema. Permanecem abertas a validação entre máquinas distintas com TLS e as campanhas com provedores reais. [Retomada rápida no mesmo canal](si022-r4-resume-lease.md) · [Migração da fila](si023-retired-session-queue.md)
