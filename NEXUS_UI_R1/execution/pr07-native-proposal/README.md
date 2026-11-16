# Proposta UI042/M3 — nova campanha isolada

Estado: preparação offline, nenhuma campanha autorizada ou executada. Esta pasta não herda consentimento, orçamento, conta, controlador ou diretórios de campanhas anteriores. O pacote final será vinculado antes de apresentar **uma única nova aprovação** ao usuário. `candidate-draft.json` não é autorização; só o hash de `candidate-final.json`, após os testes offline e o pacote final, pode ser autorizado.

O objetivo é comprovar dois harnesses distintos no mesmo projeto canônico: Codex com `gpt-5.3-codex` e Claude com `claude-sonnet-4-6` (Sonnet 4.6). São IDs explícitos publicados, sem `latest` ou escolha automática de outro modelo. O acesso da conta e a compatibilidade da versão permanecem desconhecidos até os checks/testes canônicos autorizados; um modelo indisponível causa parada, nunca fallback. Fontes: [GPT-5.3-Codex](https://developers.openai.com/api/docs/models/gpt-5.3-codex) e [configuração de modelos Claude Code](https://support.claude.com/en/articles/11940350-claude-code-model-configuration).

## Escopo proposto e sequência finita

| Ordem | Admissão | Efeito e prova exigida |
|---|---|---|
| 1 | Codex setup | Nova identidade/intent persistidos; revisão canônica, um SetupTest pago e Finish; nenhum trabalho antes do Finish. |
| 2 | Claude setup | Outra identidade/binding, mesmo `workspace_id` retornado pelo Finish de A; um SetupTest e Finish. Comparar IDs, configuração/preset e grants de A antes/depois. |
| 3 | Codex trabalho | Uma tarefa de auditoria de quatro despesas, em nova sessão explícita; resultado JSON exato e receipt SUCCEEDED. |
| 4 | Codex continuação | Verificar o total e calcular taxa hipotética de 10%, na mesma sessão, epoch e identidade nativa. |
| 5 | Claude trabalho | A mesma tarefa útil, saída separada; nenhuma interferência em A. |
| 6 | Claude continuação | Uma continuação na sessão exata de B, com as mesmas fences. |

São **no máximo seis admissões de turnos Nexus**, incluindo os dois testes de conexão. Um harness pode realizar várias requisições internas, retries ou passos de ferramentas dentro de uma admissão. O produto não oferece um teto de seis requisições HTTP faturáveis no provedor. Se essa interpretação literal for exigida, esta campanha deve ser recusada. Nenhum retry de admissão, modelo alternativo, subagente solicitado ou replay automático é permitido. Os prompts pedem cálculo apenas a partir dos dados fornecidos, sem ferramentas ou rede adicional; isso não altera nem comprova ausência de configurações nativas herdadas.

As saídas úteis esperadas são total `20.00`, quatro linhas e totais `hosting=14.75`, `software=8.25`, `refund=-3.00`; a continuação deve produzir taxa `2.00` e total `22.00`. O driver valida o JSON e só então grava artefatos próprios no projeto. Uma resposta incorreta encerra a campanha, sem uma chamada paga corretiva.

## Orçamento novo, observado e conservador

Proposta: 500.000 tokens observados acumulados para toda a campanha, sem reaproveitar saldo anterior. Antes de **cada** admissão, inclusive o primeiro SetupTest, persistir provisão de 75.000. Ela é permanente: execução terminal, relatório de uso ou período quieto **não liberam nem devolvem** a provisão. Uma admissão acima de 75.000 pode impedir concluir as seis, mesmo com total observado abaixo de 500.000; a proposta não garante que todo o roteiro caberá.

O débito preventivo é `sum(max(75000, observado_por_admissão))`; a próxima provisão só cabe quando débito + 75.000 ≤ 450.000, mantendo 50.000 de reserva. Uso correlacionado desconhecido bloqueia a próxima admissão. Durante a execução, débito acima de 450.000 ou observado atingindo 450.000 provoca contenção preventiva; 500.000 é também verificado como parada observada. Dados podem chegar tarde e ultrapassar esses limites antes de serem vistos. **75.000 não é limite nativo nem limite superior comprovado**, e 500.000 não é um teto atômico da fatura. `reported_accounting_final=false` em todos os registros.

Codex: o journal contém o contador cumulativo do thread. Usar delta a partir da base conhecida de cada admissão, sem somar snapshots cumulativos e sem somar cache/raciocínio novamente. Exigir relatório válido correlacionado à operação/turn, além da execução terminal; não afirmar que ele é uso final de billing. Claude: usar `modelUsage` do próprio resultado terminal correlacionado por operação, contando input/output/cache-read/cache-creation. Contar o relatório completo **por admissão**, sem `max(nativeSession)` entre chamadas; se um relatório streaming inclui turnos anteriores, a soma é conservadora e pode contar mais, nunca menos por deduplicação não provada. As provisões são permanentes para ambos. Fonte e limites dos relatórios: [Claude SDK cost tracking](https://code.claude.com/docs/en/agent-sdk/cost-tracking).

## Isolamento, contas e autoridade

- `identity.json` gera uma vez o UUID da campanha, root temporário, porta, dois IDs de agentes e seis client-intent IDs. Server/workspace/executor/binding/session/epoch vêm das respostas canônicas e não são inventados.
- Home do Nexus, DB, métricas, projeto, checkpoints e logs ficam no novo root. `load_config({}, flags próprios)` e ambiente filtrado impedem herdar DB/métricas/configuração Nexus pessoal. Não instalar pacotes no ambiente pessoal, serviço de usuário ou tarefa de login; usar o foreground canônico, sem encerrar/reiniciar Windows.
- A descoberta offline é exclusivamente Core `discover_installations` de PATH/layout/binários e SHA. Ela não executa `--version`, login, CLI nativo, modelo ou provedor, e não abre arquivos de autenticação/configuração/provider home. `passive-discovery.json` mostra dois candidatos, inicialmente **untrusted**. A aprovação proposta autoriza somente os roots/binários exatos vinculados, revalidados antes da execução.
- `provider_home` é uma declaração literal do home do usuário atual; seu conteúdo e a autenticação **não foram inspecionados**. Após a nova aprovação, somente os harnesses/Core poderão usar as contas já autenticadas nesses homes. Não copiar credenciais, rotacionar chaves, fazer login ou editar configuração pessoal. O próprio CLI pode naturalmente escrever estado/caches em seu home: isso precisa ser reconhecido no consentimento. Se esse home não corresponder à conta atual, parar com AUTH_REQUIRED e não reparar automaticamente.
- Não usar `--bare` como suposta solução: a documentação Claude informa que esse modo ignora login OAuth/keychain. Configurações, hooks ou MCP nativos herdados podem existir e não foram auditados. Não prometer isolamento desses conteúdos ou faturamento exato. [Claude headless](https://code.claude.com/docs/en/headless).
- Setup/Finish e execução passam por `TerminalConnection`, `TerminalWork`, `LocalOperatorHTTP` e contratos canônicos instalados. Nenhum agente recebe autoridade de operador, nenhuma aprovação nativa é automática, nenhum grant é clonado de A para B. Permissões/preset existentes são preservados; Finish é a única concessão prevista para cada nova conexão.

## Falhas e limpeza

Um root existente ou reserva `.json`/`.writing` anterior impede reexecutar. A resposta perdida mantém intent/reserva/checkpoint original; não chamar `submit`/`apply` novamente para “tentar”. Um operador pode inspecionar os receipts originais por GET, fora de qualquer nova admissão. Necessidade de decisão humana interrompe a campanha sem autoaprovação. Dados e logs privados são preservados; não publicar prompts, cabeçalhos, chaves ou conteúdo de homes nativos.

Antes da parada normal, revalidar instance/generation/PID e handle de nascimento do **próprio** foreground. Depois do prazo normal, a proposta inclui uma parada forçada canônica dessa mesma geração, somente se a identidade ainda corresponder; sem loops de reaprovação por PID. Nunca parar um Server pessoal ou geração diferente. Exigir receipt `service-shutdown.json` dessa geração em estado `DRAINED`, resultado canônico `stopped/drained`, saída física do owner/launcher e worker de dispatch encerrado. `supervisor_only`, `not_asserted` ou ausência de settlement não produzem `complete.json`. O root é preservado para auditoria.

## Preparação e execução revisáveis

1. `discover_native.py --output passive-discovery.json`: já realizado apenas na forma passiva autorizada.
2. `bind_native.py --discovery passive-discovery.json --output native-bindings.json`: declara paths/modelos, sem abrir autenticação.
3. Com o Python **instalado e isolado** qualificado, `bind_plan.py --package-report ../pr08-installed-qualification.json --native-bindings native-bindings.json --output candidate-final.json`. Só fazer o vínculo final após o último pacote; ele não aprova nada.
4. `driver.py dry-run --plan candidate-final.json --expected-plan-sha256 HASH`: não inicia serviço, não cria root da campanha nem importa handlers do produto.
5. O usuário aprova uma vez exatamente esse candidato e esta política. `consent-template.json` deve continuar falso até uma resposta nova real, registrada com referência, data e hash exatos. Autorizações históricas não servem.
6. Somente então: `driver.py execute --plan candidate-final.json --expected-plan-sha256 HASH --consent NOVO.json --expected-consent-sha256 HASH`. O driver valida consentimento/pins/contas declaradas e instalação antes de qualquer efeito.

Todos os comandos de shell desta qualificação usam prefixo `rtk`; o processo aprovado executará o Python instalado com `-I`, fora do checkout e sem PYTHONPATH de fontes. O driver não se autoinstala, não publica/deploya e não cria agendamento.

## Aceite e limites de M3

Após as seis admissões, o próprio Server permanece disponível por **até 180 segundos**, sem nova chamada produtiva, antes do cleanup. `public/observer-ready.json` publica apenas origin e IDs canônicos para outro agente observar Home, sessões e resultados reais usando a autenticação local canônica desse home temporário, sem token de provedor. O arquivo exato `public/observer.done`, com `campaign_id` correspondente e referência de evidência, encerra cedo. Arquivo/escopo diferente não é aceito; ausência até o prazo registra `NOT_RUN`, sem repetir trabalho nem autorizar turno adicional. O arquivo é uma referência do observador, não substitui sua evidência real de navegador. Falha em qualquer admissão anterior inicia cleanup imediato e não abre essa janela.

O smoke de lifecycle é separado do candidato pago: `lifecycle_smoke.py` usa outro root, PATH vazio e dois roots de instalação inertes, sem `perform`. Ele prova o foreground real pronto, DB/métricas próprios e settlement `DRAINED`/saída física, sem abrir conta ou iniciar harness/provedor. A primeira execução preservada falhou somente no oráculo SQL com nome de tabela antigo; o serviço já havia encerrado drenado. O oráculo corrigido e o resultado real estão em `lifecycle-qualification.json`.

Testes offline provam recusa, isolamento e contabilidade conservadora; **não provam** autenticação, entitlement/modelo, wire do binário instalado ou campanha produtiva. UI042/M3 permanece NOT_RUN até a nova aprovação e a evidência real. A campanha deve também registrar UI/Home e fluxo terminal de forma explícita; o driver sozinho não comprova a experiência do navegador. Remoto, Linux, Python 3.11/3.12, acessibilidade/usabilidade com pessoa externa e eventos de sessão Windows permanecem evidências separadas, não inferidas deste fluxo.

Antes de pedir aprovação: pacote final e payloads vinculados; testes offline verdes; revisão técnica deste diretório concluída; candidate-final/consent-template reconciliados. Qualquer lacuna restante deve ficar BLOCKED com seu motivo, sem transformar `technical_ready=true` em prova.
