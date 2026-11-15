# PR-05 — frontend foundation

Escopo: DTOs/adapter GET, navegação tipada, apresentação determinística, controller e hook da Home. A interface visual e o backend pertencem a entregas paralelas. Não há execução de provedor, runtime nativo ou evento do SO.

O cliente reutiliza `api.ts` (única alteração: exportar `call`) e os streams já existentes no shell. Não cria EventSource. São serializadas todas as leituras do controller; uma leitura abortada continua pertencendo à fila até seu `finally`, impedindo sobreposição com a geração seguinte. Cache vinculado a origem, identidade, workspace e filtros. O hook também mascara dados do escopo anterior no render que antecede seu efeito de configuração.

Atualização: debounce 350 ms, teto de uma leitura/s, uma invalidação pendente, fallback 15 s e vencimento por timestamps relativos ao snapshot do Server. Duração da leitura não reinicia TTL. Em background, fallback de 60 s; foco/visibilidade/reconnect retomam snapshot. Falhas parciais preservam somente itens antigos do mesmo escopo com status indisponível, total desconhecido e sem cursor. 401/403 limpam também atualizações visuais pausadas. Pausar é exclusivamente apresentação: não cancela agentes ou validações.

Paginação GET de work/results/activity/agents/external e Attention usa a mesma fila. Attention reutiliza seu endpoint/cursor e filtros canônicos (`category=action_required`, `state=active`, `seen=all`, workspace/agent). 409 reinicia pelo overview; não reenvia cursor antigo. Um snapshot novo substitui páginas antigas para não misturar revisões. IDs estáveis mantêm as identidades de render, sem inferir igualdade por título/agente.

Alvos são JSON com chaves canônicas e campos fechados, IDs opacos, workspace/Server verificados antes do resolver e identidade exata comparada na resposta. Não há URL arbitrária, seleção “latest” ou comando por navegação. Os inspetores canônicos recebem o agente resolvido pelo backend; o frontend não fabrica AttentionOccurrence nem credencial.

Os testes Node executam TypeScript transpilado do controller/apresentação/navegação e do adapter real `api.ts` com fetch controlado. Relógio manual e promises pendentes exercitam corridas, não apenas strings de fonte. Eles **não são prova DOM**, HTTP real, a11y, layout mobile, foco/scroll preservado ou desempenho da API. HOME-030/031 dependem de integração/browser/medição própria; nenhum dos 73 casos é promovido por contagem desses testes.

Resultados e pins finais em `qualification.json`; matriz de atualização em `invalidation-matrix.md`. Não há teste de browser nem alegação de limite 500 ms/2 s.
