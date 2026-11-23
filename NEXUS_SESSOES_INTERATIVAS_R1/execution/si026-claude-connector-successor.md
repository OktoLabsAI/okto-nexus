# SI-026 — Retomada salva do Claude pelo Connector

O CLI pede confirmação para retomar uma sessão encerrada. O Nexus consulta o Connector autenticado da origem e confere o recibo de fechamento, a geração, a configuração e o último resultado confirmado. O Connector responde com disponibilidade e mantém localmente o histórico, os caminhos e as configurações.

O Connector reserva a origem para uma única sucessora e confere o mesmo arquivo e perfil antes de entregar a abertura ao Core. O Core usa o UUID nativo da origem. O perfil revisado continua controlando as permissões do terminal quando o lease permite ações adicionais. Repetir o mesmo comando após a admissão consulta o recibo original.

O ensaio com o Claude Code 2.1.328 real em ConPTY usou Nexus e Connector no mesmo Windows e respostas simuladas em loopback. Uma alteração no histórico de teste foi recusada antes da admissão. Após restaurar o arquivo, a sucessora confirmou o mesmo UUID em outro processo, sem enviar prompt na abertura. O turno seguinte recebeu o diálogo anterior. Um segundo pedido de sucessora foi recusado, a repetição do comando recuperou o recibo e o fechamento canônico encerrou o novo processo.

Em duas tentativas anteriores, o fechamento concluiu e a observação do histórico ficou indisponível. O ensaio final aguardou margem no lease vigente antes de solicitar o fechamento. Outra tentativa reproduziu a recusa indevida de um perfil sem ferramentas sob um lease que permitia aprovações. A correção preserva a política do perfil e passou pelas verificações focadas do wheel final.

A regressão com o app-server Codex 0.157.0 real passou nos wheels finais. Ela confirmou a thread original, o cancelamento sem admissão, a recuperação do recibo e o fechamento da sucessora. No ensaio anterior, as asserções de execução passaram e o encerramento do servidor de teste excedeu o limite do fixture. O limite foi ampliado apenas na repetição do teste.

A mudança adiciona uma tabela privada ao SQLite do Connector na revisão 6, sem migração no banco do Nexus. A reversão usa os pins e commits anteriores em conjunto. Os endpoints só negociam a retomada do Claude se os dois lados anunciarem suporte. [Registros e hashes](si026-claude-connector-successor.json)
