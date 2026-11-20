# SI-T-C06 — Reorientação antes de o Claude começar a gerar

Com o Claude Code 2.1.328 retomado e o primeiro turno aguardando o início da resposta, a API omitiu a confirmação de reorientação. O catálogo apresentou a ação como indisponível para o estado atual. Dois pedidos concorrentes dirigidos à operação exata receberam HTTP 409. A consulta por recibo retornou HTTP 404 para os dois pedidos.

O terminal recebeu zero escritas de interrupção ou substituição enquanto aguardava a resposta. O mesmo processo continuou ativo, com apenas o pedido original ao provedor simulado. Depois de observar o início da geração, o ensaio obteve uma nova revisão e enviou uma única confirmação explícita. O processo registrou um Esc e uma substituição na sessão original, nessa ordem. A auditoria do SQLite confirmou um único controle admitido e nenhum registro de intenção ou entrada para as recusas. O controle de fechamento encerrou a sessão. [Dados do ensaio](si026-claude-requesting-refusal.json)

O ensaio usou wheels instalados, HTTP via TestClient, o executável Windows arquivado com perfil descartável e SSE simulado em loopback. A instalação atual apontava para outro hash. Usei uma cópia da versão já qualificada com seu hash conferido. O marco registra evidência e dispensa migração. Para desfazer o registro, reverta o commit.
