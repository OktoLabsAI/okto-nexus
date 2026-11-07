# Refresh de propostas — somente preparação

M1 v2 e Windows duas tarefas são propostas separadas. Nenhum aceite M1, execução nativa de provider ou mutação de serviço foi feito. A proposta Windows usa os três wheels candidatos SVC07; a qualificação instalada final continua a cargo do root e não é inferida dos checks desta pasta.

Checks fechados: venv próprio sem system-site-packages, instalação offline de dependências previamente pinadas (MCP 1.30.0), pip check, oito import/help checks, igualdade source/wheel/install de 691 arquivos Nexus, 124 Connector e 166 Core, e leitura dos dois nomes exatos abaixo. Ambos estavam ausentes. Nenhum registro, start, enable, stop ou delete de Task Scheduler foi chamado.

- Nexus: `OktoNexus-server-8bfef9d6027a66372f8a7740fe8b0f3cffe7cbeb16a8a0eeff2084be2b53de9b`
- Connector: `OktoNexus-connector-803538d0fe8d0385e7509b2101331869b261ad04581caeb47e5fce03bb66570b`
- Loopback aprovado apenas como proposta: 127.0.0.1:52106.
- Roteiro: 24 ações finitas, 12 por componente (install, repeated install, start, reuse, disable, stop, recusa de start desabilitado, enable, start, restart, stop, uninstall).

O primeiro driver concluiu todos os oito checks e as duas leituras, mas não encontrou git no PATH isolado. O log bruto permanece byte a byte, inclusive sua codificação original. O finalizador usou esses reports fechados e metadata de repositório obtida separadamente; não repetiu imports ou acesso nativo. Isso foi falha da preparação, não do produto ou campanha.

O M1 v1/manifesto anterior permaneceu igual. A v2 acrescenta report.json em diretório irmão descartável, sem ampliar política ou sandbox. Se não surgir pedido nativo verdadeiro, esse caso permanece pendente. A pergunta sobre 200 mil rígidos versus interrupção preventiva aos 100 mil reportados ainda não representa resposta nem autorização.

Arquivos desta pasta são curados por allowlist. Wheels, venv, profiles, homes, bancos e material de autenticação estão excluídos. Os scripts são evidência revisável de preparação; não são um autorizador nem runner da campanha.
