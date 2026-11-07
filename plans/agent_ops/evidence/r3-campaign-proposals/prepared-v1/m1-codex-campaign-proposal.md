# Proposta M1 Codex CLI — preparada, não autorizada nem executada

A campanha proposta é finita: um ciclo local e outro executado pelo Connector, ambos pelo terminal e com decisão nativa real. Nenhuma inferência, leitura de credencial, processo nativo ou serviço foi iniciado nesta preparação. A informação de que a conta já está autenticada e o limite total de 200 mil tokens orientam esta proposta; não autorizam a execução.

## Artefato concreto disponível

O [release oficial 0.157.0](https://github.com/openai/codex/releases/tag/rust-v0.157.0) foi baixado exclusivamente neste Temp. O ZIP tem SHA256 `6c74e2019583cc16e55f79161ef795c8ff712709ad9ed832b3a5b87a7eacdef6`. O executável interno tem 322525488 bytes e SHA256 `ed1c7b36e44536809c868864c833af8a857f56599a7a7fe23b908a1ba1093b1f`, igual ao build qualificado no Core. As funções puras atuais confirmaram conversa e controles; o único pedido nativo qualificado desse build é `item/commandExecution/requestApproval`. Nenhum executável, helper de sandbox ou postinstall foi rodado.

A igualdade é pelo fingerprint de conteúdo do executável. O `build_identity.v3` calculado (`0bf80fe3…26535`) não coincide com o grant portátil histórico (`df63d86e…edcb`). Não foi alterada allowlist: o ramo atual de `qualified_build` aceita o fingerprint exato, e `discovery.fingerprint()` realmente retorna o SHA bruto. A aprovação canônica do novo caminho/projeto continua necessária. Os dois comprovantes JSON preservam separadamente a tentativa inicial de comparar apenas a identidade portátil e a verificação correta pela API pura.

O 0.167.0 pessoal permanece intacto e não recebe capacidade por inferência. O 0.159.0 estável não basta para a decisão representativa: só tem os controles qualificados. O alpha 0.159.0-alpha.12.1 tem `requestUserInput` qualificado, mas não foi escolhido nem baixado.

## Etapas e efeitos revisáveis

1. Pinar wheels instaladas finais do SVC07, imports, ambiente, dois projetos descartáveis e os alvos de serviço por usuário. Os hashes finais ainda estão pendentes; a proposta anterior de serviço é referência histórica, não autorização nem fonte de hashes atuais.
2. Fazer `connect --plan` local, rever candidato físico, identidade, workspace, preset e contexto efetivo. Aprovar só a revisão exibida e usar `--no-chat`. O teste de conexão local já pede resposta ao modelo e entra na conta de tokens.
3. Pedir um trabalho pequeno: ler `numbers.csv` contendo 1, 2, 3, 4 e apresentar contagem 4, soma 10 e SHA256. Observar uma permissão nativa real. Aprovar somente comando exato de leitura/cálculo nesse projeto; se o pedido divergir, negar/parar. Texto do modelo não comprova uma permissão. Se a política efetiva não produzir o método qualificado, o caso fica pendente, sem turnos extras para forçá-lo.
4. Fechar e reabrir o cliente de terminal, recuperar mesmos IDs e resultado, e realizar no máximo uma continuação curta explicitamente solicitada. Sair do cliente não interrompe trabalho. Retomar contexto nativo após perda do processo só se o contrato específico comprovar suporte; nenhuma sessão nova disfarçada de retomada.
5. No host Connector, exportar o rascunho não secreto com `--setup-draft`; o operador humano usa `OperatorProfile`, revisão persistida e Finish existentes. A chave do agente passa apenas pelo mecanismo protegido existente; cookie/chave de administrador não vai ao host. A conexão concluída é retomada sem repetir probe, Finish ou concessões.
6. Repetir o trabalho e a decisão pelo caminho real HTTP/WebSocket/Connector/Core. Aplicar uma perda controlada de resposta depois da admissão canônica e, se houver controle técnico demonstrável, uma depois do ACK da decisão. Recuperar checkpoint/IDs anteriores; nunca emitir novamente com ID novo para sanar incerteza. A falha de rede é injeção declarada em cliente temporário, não falha natural nem mock do provider.
7. Reabrir o cliente, conferir resultado e cardinalidade dos efeitos, e fazer no máximo uma continuação explícita. Fechar sessões canonicamente, drenar serviços, verificar saída dos PIDs/births possuídos e desinstalar só os alvos temporários previamente aprovados.

O JSON contém os comandos e gates por etapa. São templates revisados pelo parser, não comandos executados. Valores gerados em revisão (`candidate_ref`, revisions, IDs) não são inventados. O máximo proposto é 6 admissões produtivas, contando eventuais testes de conexão; execução serial, sem retry automático de turnos e sem subagentes. Isso limita o roteiro, não garante um limite de tokens por turno.

## Teto de tokens: impedimento explícito

O contrato atual **não comprova um teto rígido agregado de 200000 tokens**. `TurnStartParams` não contém limite de saída/tokens; as configurações portáveis também não. `thread/tokenUsage/updated` chega depois de computação, e `interrupt`/contenção não são uma transação atômica com a contagem de tokens. Nem um roteiro curto nem uma margem grande eliminam a possibilidade de ultrapassagem.

A [documentação do app-server](https://learn.chatgpt.com/docs/app-server), consultada pelo root, e o schema local descrevem uso por thread e `thread/goal/set`. Este último cria estado persistente e não foi comprovado como hard cap da campanha; não será usado como atalho.

Se o usuário aceitar um limite **operacional**, a proposta é não admitir novo trabalho após 100000 tokens observados e solicitar interrupção após 120000 tokens ou 120 s de um turno, mantendo margem ao valor solicitado. Ainda pode haver overshoot; essa interpretação exige esclarecimento antes de qualquer inferência. Se 200000 for limite rígido, a campanha fica bloqueada até existir uma garantia efetiva aplicável ao fluxo, sem substituir o requisito por promessa.

A contagem deve estar armada antes do primeiro teste de conexão. Por thread nativa, manter high-water de `tokenUsage.total.totalTokens` e somar só deltas, sem duplicar notificações, `last`/`total` ou parcelas de cache/raciocínio. Mapear stream epochs ao mesmo thread; retomada do mesmo thread não reinicia contagem. Ausência/gap/regressão ou falta de eventos do teste de conexão significa total incompleto: impedir novas admissões, interromper/fechar somente o trabalho possuído e reportar mínimo conhecido. O coletor e a injeção de resposta ainda precisam ser implementados e revistos contra a wheel final; não são alegados como instrumentação pronta.

## Contexto e limites que continuam abertos

- A execução nativa pode ler a autenticação/configuração de seu `provider_home` e escrever seu próprio histórico ou refresh. Executável e workspace em Temp não isolam automaticamente o login. O agente não leu e não copiará nem divulgará esses arquivos; o contexto exato e seu uso nativo precisam de autorização explícita.
- O modelo, instruções, tools, sandbox, approval policy e MCPs efetivos devem vir do fluxo canônico. Não foi presumido que o serviço herdou o shell, nem que o preset altera esses valores. Alterar configuração pessoal manualmente não é saída para fechar o percurso padrão.
- O Connector proposto usa processos/homes separados em loopback: prova a topologia de execução remota por protocolo, não rede entre duas máquinas físicas. Não promove M2 nem campanhas multiplataforma.
- O caso de permissão usa somente o método previamente qualificado. Não amplia suporte de input, fileChange, elicitation ou 0.167.0. Não modifica projetos pessoais, não instala dependências por instrução do modelo e não concede autorização ampla de comandos.
- Publicação só de metadados, hashes, contagens, IDs e estados sanitizados. ZIP/executáveis, homes, bancos, auth, cookies e respostas brutas potencialmente sensíveis ficam fora da curadoria pública.

Mapeamento do plano: M1/DX-T39 local; M1/DX-T40 Connector; DX-T43 contexto efetivo; DX-T45 decisão nativa; DX-T46 perda/recuperação sem duplicação; DX-T47 retorno do terminal; DX-T50 sem dashboard obrigatório. Nenhum desses aceites foi promovido por esta preparação.
