# UI-010 — protocolo focal do shell (PREPARED, NOT_RUN)

Preparado após UI-009; aguarda aviso explícito do root de bundle final e fonte
congelados. Nenhum browser, fixture ou provedor foi iniciado por este protocolo.
Qualificação do shell é independente da Home unificada, UI-019, segundo harness,
onboarding múltiplo e gates de release/campanha, que não são promovidos aqui.

## Superfícies e isolamento

Reutilizar skill Playwright CLI e infraestrutura existente
`tests/home_evolution/browser_fixture.py` (seed17handoffs, lifespanoff, loopback
com porta automática, stop/ready próprios, sem runtime/provedor). Criar controle
Temp com prefixo específico UI-R1 e sessão CLI headless Chrome exclusiva.
Nunca reutilizar browser/perfil/conta/banco pessoal ou instalação do usuário.
Não editar assets à mão nem fazer build por este runner: executar somente o
bundle que root congelar, fixando HTML+JS/CSS e arquivos de fonte relevantes.

Runner finito, com stopfile/finally e prazo total registrado. Ready deve preceder
captura e fixar SHA de produto, registry/componentes/shell e fixture. Navegação
normal é GET; registrar todo método não GET. A fixture padrão bloqueia mutações:
isso não comprova recebimento de uma ação que recebeu405.

T-NAV-09 exige exceção separada: entrar em Conversations pode chamar a marcação
canônica de mensagens do operador. Antes de exercê-lo, preparar variante finita
da mesma fixture com allowlist explícita somente desse endpoint canônico e DB
próprio. Capturar watermark/estado antes/depois de Home/Conversations; não
interceptar POST como sucesso e não afirmar0POST nesse subcaso. Sem essa variante,
registrar T-NAV-09 NOT_RUN com motivo. Não alterar produção para fazer a prova.

## Checks propostos contra navegação real

1. **T-NAV-01/02**: desktop1440, Home clássica (flag operacionalOFF), menu aberto:
   exatamente Home/Conversations/Graph/Artifacts e Advanced secundário; data-view
   mantém `Meta-harness`, nenhum menu adicional Harnesses/Executions/Sessions.
   Repetir shell com Home operacionalON sem alegar nova Home unificada.
2. **T-NAV-03**: Advanced mostra os quatro grupos; abrir páginas por callbacks
   reais, confirmar rótulo, breadcrumb Advanced→Grupo→Página e só cinco botões
   na sidebar. Preservar workspace. Não acionar edição/configuração/test connection.
3. **T-NAV-04/05**: aliases antigos e rótulos públicos já têm teste de contrato.
   No browser usar somente caminhos realmente suportados no HEAD. O shell atual
   não possui bookmark arbitrário por nome de view: não inventar `?view=Policies`
   para fingir compatibilidade. MemoryOFF não aparece; MemoryON requer variante
   de config própria real. Não habilitar feature na instalação pessoal.
4. **T-NAV-07/08**: Home operacionalOFF com pendência real do seed, sino global
   disponível em Home/Graph/Artifacts. Abrir fila e inspeção canônica sem responder,
   aprovar ou alterar preferências. Contagem global não muda por workspace/filtro
   resolved/snoozed da fila; fila informa seu escopo. Se o seed não tiver o tipo
   necessário, preparar fato válido canônico próprio e não promover cenário
   específico de aprovação apenas com outro tipo de ocorrência.
5. **T-NAV-06**: autoridade exige recusa real da API canônica. Fixture read-only405
   não é401/403 nem prova ACL. Usar cliente HTTP/browser isolado sem credencial ou
   cenário HTTP de auth canônica já preparado, sem conta pessoal. Interceptar
   resposta401/403 só qualifica limpeza/estado UI, nunca autorização backend.
   Capturar corpo protegido ausente, guard e efeito não aplicado.
6. **T-NAV-12**: viewport360 antes de carregar, abrir menu por nome acessível,
   navegar pelos quatro destinos e Advanced por teclado/clique, menu recolhe;
   foco fica em destino coerente, aria-current correto. Esperar transição terminar,
   conferir hit-test central do controle (não só bounding box). Document/containers
   sem overflow horizontal obrigatório; capturar menu aberto e destino/painel.
   Uma captura de360CSSpx não comprova zoom nativo200% ou leitor de tela.
7. **T-A11Y-01**: tabulação, labels, foco/retorno, breadcrumb e sino com estados
   desconhecido/stale claros; um único dialog ativo, Escape/guard preservados.
   O que exige fala AT/humano permanece NOT_RUN até observação real apropriada.
8. **T-NAV-10**: round-trip do `home_target` legado pode ser exercido no corte
   atual com alvo realmente resolvido. A metade `kind:session` fica NOT_RUN até
   UI-019; erro não pode abrir substituto. Não chamar o cenário inteiro PASS.

## Evidência e saída

Por check: resultado PASS/FAIL/NOT_RUN, viewport, IDs/rótulos/escopo observados,
requisições/respostas relevantes, captura e limites. Registrar console/pageerrors
e distinguir falha de produto de fixture não compatível. Não aceitar500/503 de
fontes ativas como execução limpa. Sem inferir campanha/AT/retomada de harness.

Ao terminar, navegar about:blank e fechar somente a sessão CLI própria;
comprovar close0 e ausência do PID próprio. Criar stopfile, aguardar terminal0
do fixture e confirmar porta liberada. Preservar logs/ready/hashes/capturas e
qualificação mínima. Não inventar exit0 se só perdeu handle. Não iniciar rodada
nova por ausência de handle sem verificar o estado atual.
