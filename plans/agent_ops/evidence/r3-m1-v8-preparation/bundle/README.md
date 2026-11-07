# M1 v8 — proposta para revisão humana

A execução ainda **não está autorizada**. É um novo ciclo fresh com Codex0.157.0
usando a conta já autenticada em C:/Users/jpamb/.codex. O agente não lê nem copia
credenciais, configuração pessoal ou transcritos. A v7 foi encerrada; sua aprovação
não cobre a nova instalação, tarefas e limites propostos aqui.

A proposta inclui:

- Instalar offline as três wheels qualificadas em um novo venv que hoje contém
  somente dependências. A instalação de produto será cronometrada e terá reserva
  durável contra repetição; não foi executada nesta preparação.
- Duas tarefas Windows novas: install/start/stop/uninstall em cada uma, oito
  comandos explícitos no arquivo proposed-commands.json.
- No máximo um ensure/start implícito da mesma tarefa Connector durante o único
  connect de configuração. O caminho pronto reutiliza o owner; o caminho de
  Scheduler pode iniciar essa tarefa. FG=1 vale somente para o consumidor e
  recusa fallback detached. Identidade/supervisor são conferidos antes e depois.
- Até seis admissões novas, oito cumulativas com as duas anteriores; carry-in de
  45.843 tokens observados, preventiva cumulativa proposta200.000, tolerância
  cumulativa700.000 e prazo120s serial. Slots não usados não viram tentativas extras.
- Um trabalho útil e uma continuação por topologia, fixture restrito e decisões
  nativas reais somente após revisão exata. Recuperação usa os mesmos IDs via GET.

Os homes permanecem sob Temp/m1-fresh-v8-pg0b6zbf/campaign, porta49807.
Preflight é observação momentânea, não trava atômica do sistema. Mudança de geração
só é aceita após confirmar a mesma tarefa/instância supervisionada; nenhum trabalho
remoto começa sem novo exame do owner e Finish canônico.

O bootstrap usa o CLI interativo real em ConPTY: produtor e consumidor coexistem
para completar materialização/Finish. O plaintext da chave nova fica somente em memória no transporte e segue pelo credential-stdin canônico, com persistência pelo vault canônico do Connector; sem plaintext em log, arquivo ou argv.
O consumidor omite --non-interactive e usa --no-start-at-login. O Job contém
apenas os CLIs auxiliares e probes efêmeros de versão/protocolo, sem turno de modelo.
Somente esses filhos próprios podem ser encerrados no deadline do helper.
**Força de serviço, kill de daemon, sessão produtiva dentro do Job, breakaway e
replay estão excluídos.** Callback de stop e cleanup compartilham a mesma reserva;
um timeout não permite emitir outro stop.

Cada script recebe o snapshot e seu SHA final, além do recibo real de aprovação
com SHA próprio. Sem aprovação exata, recusa antes de importar produto, consultar
bindings, criar homes ou executar processos. O controlador mantém os cumulativos
sem alterar o fault/checkpoint anterior. A publicação repetida de uso e de pergunta
nativa tolera somente erros Windows5/32; persistência privada e decisões continuam
fail-closed. Falha de publicar a pergunta impede enviar a decisão naquele poll.

DX-T43 preserva somente metadados Core reportados, obtidos por GET canônico dos
eventos, incluindo replay desde0 quando necessário. instructionSources são
referências, não conteúdo lido; metadados não provam enforcement ou inventário
completo de ferramentas. Ausência/invalidez continua desconhecida. A reabertura do
observador/CLI não será apresentada como reconexão física do host. BASE-06 usará
início da instalação de produto e resultado útil com relógios monotônicos; a
preparação anterior das dependências é separada e não há alegação antecipada de15min.

Para revisão/curadoria: m1-codex-campaign-proposal-v8.json,
proposed-commands.json, source-proof.json, installed-fg-guard-result.json,
guard-result.json, controller-review-addendum.json, final-preflight.json,
publication-adaptation.json e os scripts listados no manifesto. A proposta
aponta aos artefatos qualificados de controlador, Core, PTY e instalação offline.
O manifesto fecha os hashes; os recibos reais só serão criados depois da aprovação.

Esta revisão substitui somente a preparação anterior: o snapshot eeff7487… foi
rejeitado na revisão por uma corrida entre impressão da chave e exportação do
handoff, e permanece imutável. O consumidor agora aguarda também o anúncio
público exato emitido depois da gravação atômica do handoff. O produtor continua
sendo drenado e o prazo único permanece. Nenhuma execução real foi realizada.
