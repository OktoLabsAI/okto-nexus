# Auditoria final do ledger

**Sem achados bloqueantes de rastreabilidade ou promoção indevida.** Revisão somente leitura do [ledger](../NEXUS_QUICK_CONNECT_LEDGER_R1.json), gerador, [entrega final](final-delivery.md) e relatórios citados. Nenhuma suíte, gerador, provedor ou autenticação foi executado; nenhum desses três arquivos, fonte, teste ou prefixo foi alterado.

## Conferências independentes

Os XMLs dos três cortes finais reproduzem exatamente o mapa `exact_nodes` da reconciliação, sem duplicatas: shard 0 **164 PASS/8 SKIP**, shard 1 final **394 PASS**, legados **3 PASS**. Total **561 PASS/8 SKIP/0 FAIL/0 ERROR**. Os três hashes de qualification são iguais aos fixados na reconciliação. Há oito nodes de cancelamento e dezessete de renderer efetivamente PASS. Os oito skips continuam literalmente `skipped`: três testes POSIX em Windows e cinco testes dependentes de terminal na execução com PIPE.

As duas provas finais de console são separadas desses totais: Ctrl-C130 e resize/confirmar/retomar passaram em consoles próprios do wheel final. Não converteram os cinco PIPE skips em PASS. C15 mantém a prova anterior de filesystem WSL2 e a respectiva versão; H09 agora inclui o helper instalado, PowerShell 7.6.10 e `sh`/dash no WSL. PowerShell 5.1 recusa antes da invocação; cmd não é anunciado como suportado.

O candidato `9bc4034663ca63cfee43790b4bc03c38f8bdebcc`, wheel `d2c322168d56e87bde22cfe262d5d2fbc9a5737b0572144774894624d561cf88` e payload **1.028 = 733 Nexus + 168 Core + 127 Connector** conferem com QC36. A comparação read-only do a36 com o novo wheel encontra alterações somente em `connect.py`, `quick_connect_outcome.py` e o novo `quick_connect_render.py`; não atribuí o console/renderer final ao wheel anterior. Os 202 casos WSL anteriores permanecem explicitamente no corte a36.

O ledger contém **146 cenários PASS/1 BLOCKED**, **31 tarefas VERIFIED/1 IMPLEMENTED/1 BLOCKED** e **19 requisitos VERIFIED/R20 PARTIAL**. Todos os caminhos de evidência dos requisitos, tarefas e cenários existem. `finalize_technical_gate` preserva QC-031 BLOCKED, QC-033 IMPLEMENTED/G6 não aprovado, R20 PARTIAL e os gates independentes; as flags finais agora apontam provas realmente concluídas. O gerador não foi executado por esta auditoria.

## Gates preservados

- I09/QC-031 e a guarda UNKNOWN continuam bloqueando a campanha real; nenhuma prova sintética ou shell inerte libera provedores. A exclusão de Claude refere-se à campanha real, não à gramática suportada.
- I08 passa no aceite literal de artefato/entrada/dependências. A regressão ampla permanece **NOT_GREEN**, inclusive shard 3 original **1.821 PASS/36 FAIL/54 SKIP**, hangs, remainders e filhos com proveniência mista. Os dois cortes shard 1 finais anteriores continuam falhos/incompletos, sem causa retrospectiva inventada para o fallback Git.
- O release decision original UI-R1 segue `approved=false`. A entrega não promove automação de browser/console a aceite humano, AT, fala, eventos de sessão Windows ou qualificação universal de OS/Python/PTY.
- A reconciliação declara o limite dos filhos aninhados; origem dos imports parent e cópias sem `src` não viram uma afirmação universal sobre todos os processos transitórios.
- A CI remota de `9bc40346` está observada como **queued/conclusion=null**. Não há conclusão de CI promovida e esta auditoria não aguardou nem disparou outra execução.

O [final-checks](final-checks.json) registra 1.804 pins sem drift, Ruff E4/E7/E9/F e diff-check do escopo declarado PASS. Seu scanner percorreu 2.274 arquivos/45.195.975 bytes sem matches **das regexes configuradas**; isso não é garantia universal de ausência de segredo. Esses são resultados reportados pelo Root e conferidos no artefato, não execuções repetidas nesta auditoria.

## Uma observação não bloqueante

`QC-T-I08.execution_notes` ainda descreve QC11/12/13 com 1.027 payloads. A mesma entrada inclui corretamente QC36 final com 1.028. A frase é verdadeira como antecedente; opcionalmente explicitar “antecedente” e acrescentar a contagem final melhora a leitura atual. Não exige mudar o PASS, apagar evidências históricas ou alterar o gate broad.

Os hashes de todos os inputs lidos, verificações e essa observação estão em [final-ledger-review.json](final-ledger-review.json). Este parecer valida a coerência da entrega técnica delimitada; não aprova release/deploy nem os gates retidos.
