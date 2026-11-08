# Proposta M1 v10 pronta para autorização

A v9 autorizada foi executada e encerrada com parada normal e remoção da tarefa, preservando os dados. O setup passou; o trabalho útil falhou antes da admissão nativa. M1 continua pendente.

A v10 é uma nova campanha finita. O diagnóstico de erros SQLite foi ampliado, a observação de uso foi separada da API e a parada remota agora espera o encerramento dos auxiliares antes de parar os serviços. A causa específica do DB_ERROR histórico ainda não foi comprovada.

- Conta: a já autenticada no Codex CLI; executável qualificado 0.157.0, sem alterar a instalação pessoal.
- Limites: 200.000 tokens observados como barreira preventiva e tolerância operacional acumulada de 700.000. O mínimo histórico de 67.658 permanece contabilizado; não é faturamento final nem limite rígido do provedor.
- Execução serial: prazo operacional de 120 segundos por turno; cinco novas reservas previstas e teto conservador de seis, sem reaproveitar vagas. As cinco reservas históricas são preservadas; teto acumulado de onze.
- Duas tarefas temporárias próprias, oito ações explícitas de instalação/início/parada/remoção e no máximo uma partida implícita da mesma tarefa Connector.
- Uma conta de operador temporária no servidor isolado e uma transferência protegida de credencial. Nenhuma credencial pessoal será lida pelo agente.
- Sem replay, reinício adicional ou parada forçada de serviço. A limpeza forçada, se necessária, limita-se ao Job dos processos auxiliares e torna a transferência não confirmada.
- Resultado esperado: relatório JSON correto em cada topologia, uma decisão nativa real por topologia quando solicitada pelo runtime, recuperação dos mesmos IDs e uma continuação por topologia. Loopback não comprova uma segunda máquina física.

Os testes offline, a revisão independente e as recusas sem autorização estão em `public/`. Os componentes PTY e observador, inclusive tentativas com falhas, também foram preservados nos milestones anteriores. Esses testes não encerram M1 nem BASE-06.

É necessária uma autorização nova porque a proposta v9 encerrada limitava a campanha anterior a nove reservas acumuladas. A v10 propõe novas tarefas e até onze reservas acumuladas; os limites de tokens permanecem os já combinados.

[Proposta exata](public/draft/m1-codex-campaign-proposal-v10.json) — SHA-256 `90c2ed2ca18e7fd86380c614e516a5f8975af2a2052b56a3609004be4814405a`.

Nenhuma instalação de produto no destino, conta, tarefa, serviço ou inferência da v10 foi executada. Após aprovação, os hashes, a ausência das tarefas e a disponibilidade da porta serão conferidos novamente.
