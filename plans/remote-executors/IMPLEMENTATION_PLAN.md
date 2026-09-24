# Executores remotos do Nexus

Status: PLANEJADO — implementação não iniciada.
Data: 2026-09-24. Branch de trabalho: `feature/v0.2.0`.
Baseline documental: `c8d148d`; runtime local de referência:
`ad4b2b3a82d3e8b3bd4d5107b39db32c427785ec`, versão 0.2.0,
surface 60 / identity docs 27 / schema 65.

## Objetivo e resumo da proposta

Permitir Nexus na máquina A e harnesses nas máquinas B e C, preservando
identidades canônicas, permissões, inbox e os quatro conectores existentes.
Instalar um executor leve em cada máquina que hospeda processos. O Nexus
central continua responsável por autenticação, autorização, roteamento,
entrega lógica e auditoria. O executor administra somente os runtimes locais
e o transporte de operações e eventos autorizados.

```text
Máquina A: Nexus — agentes, políticas, inbox, sessões, auditoria
    ^                           ^
    | canal autenticado TLS     | canal autenticado TLS
    | iniciado por B            | iniciado por C
Máquina B: executor          Máquina C: executor
    Codex / Pi                  Claude stream / attach suportado
```

O transporte proposto é WebSocket sobre TLS, iniciado pelo executor; B e C
não precisam expor portas. Essa é uma decisão de projeto a validar em R00,
não uma capacidade já implementada. Os protocolos dos harnesses continuam
locais: Pi/RPC, Codex/app-server, Claude/stream-json e Claude/attach cc-socks.
Nenhum deles precisa implementar MCP para ser hospedado por um executor.

Hoje, MCP ou REST remoto abre o runtime no servidor Nexus. O código constrói
o conector localmente em `RuntimeOpenService.open`, com guarda do proprietário
ativo de `serve`. O proxy de owner existente não é um executor remoto.
Ver [limites atuais](../pr34-remediation/SELF_CONNECTIONS.md).

## Escopo e limites

- Incluir executor remoto e executor local embutido sob contratos comuns;
  pareamento, inventário, abertura, eventos, múltiplos turnos, steering,
  interrupt e encerramento quando o adaptador oferecer essas capacidades.
- Manter boot e abertura sob demanda, com destino explícito e autorizado.
- Permitir attach somente onde protocolo, plataforma e alvo aprovados
  realmente suportarem. Não adotar conversas existentes de Codex, Pi ou
  Claude stream por inferência.
- Não criar outro Nexus completo por máquina, servidor A2A, broker externo,
  sincronização automática de repositórios ou novo orquestrador de tarefas.
- Código, arquivos e dependências do projeto precisam existir na máquina
  escolhida. Caminhos de B não são caminhos de A. Transferência de artefatos
  fica restrita aos mecanismos existentes e às permissões correspondentes.

## Identidades e autorização

| Entidade | Significado e autoridade |
| --- | --- |
| Agente | Identidade lógica canônica existente; não muda ao trocar de máquina |
| Executor | Máquina/instalação aprovada para hospedar endpoints específicos |
| Endpoint | Associação do agente, método, executor e perfil aprovado |
| Sessão | Execução de um endpoint sob um responsável e geração de controle |

O operador cria um convite de pareamento curto, de uso único, com expiração.
O executor gera sua própria identidade criptográfica; o pareamento vincula a
chave pública à aprovação do operador. Não imprimir ou persistir convites em
logs. A forma final de emissão/rotação de credenciais (por exemplo, certificado
cliente ou prova de posse) deve ser decidida em R00, usando primitivas e
bibliotecas mantidas, sem criptografia própria.

Uma credencial de executor não é credencial de agente nem chave de operador.
Ela não permite autoatribuir `agent_id`, criar grants ou acessar toda a inbox.
Uma operação precisa vincular executor, agente, endpoint, sessão quando
existente, ação, revisões aprovadas, prazo e geração de controle. O Nexus
revalida a autorização ao admitir e despachar. O executor verifica o vínculo,
o prazo, a geração e suas próprias restrições antes de qualquer efeito local.
Mudanças de perfil exigem revisão/aprovação; não aceitar comandos arbitrários
ou configurações de processo trazidas pelo payload do agente.

MCP, REST e comandos internos usam o mesmo caso de uso e a mesma autorização.
A chave de conexão atual continua tendo seu escopo; não deve ser promovida
a credencial de executor. Seu TTL global de 24h, override por agente e opção
sem expiração permanecem separados da duração curta das autorizações de
execução e do pareamento.

Segredos de providers ficam no executor, configurados explicitamente para o
perfil aprovado. Nunca transmitir a chave administrativa aos subprocessos.
Preservar sandbox e approvals. Um executor comprometido pode observar os
processos que hospeda: a aprovação da máquina é uma fronteira de confiança,
não uma promessa de isolamento contra o administrador daquele host.

## Contrato versionado proposto

Nomes abaixo são lógicos; mapear para mecanismos existentes antes de criar
módulos ou tabelas. Negociar versão e capacidades; rejeitar versões
incompatíveis, sem fallback que reduza autorização.

- Handshake: identidade do executor, versão de protocolo, plataforma e
  capacidades declaradas. Capacidade declarada não concede permissão.
- Operação: `operation_id`, hash do conteúdo, ação, executor/endpoint/agente,
  sessão opcional, revisões, geração e validade. Mesmo ID com conteúdo
  diferente é conflito; mesmo ID só retorna estado já registrado.
- Eventos: identidade de sessão validada, geração, sequência e tipo.
  Separar recebimento durável pelo executor, início do processo, aceitação
  comprovada pelo harness, processamento e conclusão de handoff.
- Controle: limites de tamanho, concorrência, armazenamento e taxa;
  heartbeat, cursor de eventos e reconciliação explícita.
- ACK do canal confirma somente a etapa documentada. Não inventar ACK,
  retomada ou deduplicação do protocolo nativo.

O supervisor local cuida da árvore de processos e proteção contra órfãos.
O journal local registra operações/eventos com durabilidade e retenção
limitada; não constitui uma segunda inbox ou fila autônoma de tarefas.
Persistir intenção antes do efeito, executar processo/rede fora da transação
SQLite e persistir o resultado depois. Usar concorrência limitada.

## Desconexão, duplicação e retomada

Estados propostos do executor: pendente, online, desconectado e revogado.
Ausência de heartbeat significa indisponibilidade de controle; não comprova
que os processos terminaram. Estados de operação distinguem reservado,
recebido duravelmente, em início, ativo, encerrado, falha definitiva e
resultado desconhecido, adaptados aos estados canônicos existentes.

Cada sessão tem um executor responsável e uma geração monotônica de controle.
Comandos de geração antiga são recusados. A geração, sozinha, não para um
processo isolado pela rede: o executor aplica um prazo local de autorização
e a política aprovada para perda prolongada de contato. O padrão proposto
é suspender novas operações imediatamente e encerrar os processos gerenciados
ao fim desse prazo; se não for possível provar encerramento, manter estado
incerto e impedir substituição automática. Attach exige política específica
de detach/interrupt; não matar processo externo por suposição.

No retorno do canal, reconciliar journal, sessões e cursores antes de admitir
novas operações. Eventos repetidos são deduplicados no transporte; lacunas
irrecuperáveis são registradas como lacunas. Operação possivelmente aceita
pelo harness nunca é repetida automaticamente sem deduplicação ou reconciliação
comprovada. Não prometer execução exatamente uma vez.

A inbox permanece a entrega lógica central. Selecionar um endpoint para cada
tentativa autorizada; não executar em B e C simultaneamente por padrão.
Outbox acompanha tentativas. Mensagem conversacional não autoriza tarefa;
handoff continua sendo o mecanismo de trabalho executável.

## Interface e experiência operacional

Nova área **Executores/Máquinas**: pareamento, aprovação, status, última
atividade, plataforma, capacidades, rotação e revogação. Não exibir segredos.
Em **Agents → Connections**, adicionar **Executar em: esta máquina / B / C**;
mostrar perfil, diretório e disponibilidade relativos ao destino.

O usuário aprova executor e perfil antes da primeira abertura. A descoberta
via MCP/REST passa a informar destino, disponibilidade e motivos de bloqueio,
sem vazar caminhos privados, segredos ou endpoints de outros agentes.
Os comandos copiáveis devem deixar claro em qual máquina o runtime será
iniciado. Trocar o destino de endpoint ativo exige encerramento/reconciliação
explícitos; não migrar silenciosamente uma sessão.

## Fases, dependências e evidências

Todas as fases abaixo estão PENDING. Não iniciar runtimes reais por padrão.

| ID | Depende | Entrega e gate |
| --- | --- | --- |
| R00 | — | Inventariar owner, supervisor, journal, boot, grants, inbox/outbox e adaptadores; threat model; decidir credenciais, TLS, prazos e protocolo v1; reproduzir baseline local |
| R01 | R00 | Extrair contrato de execução; implementar executor local embutido preservando comportamento; provar composição real serve/MCP/REST e quatro adaptadores |
| R02 | R01 | Migrações aditivas, pareamento, aprovação, credenciais/rotação/revogação e escopo por executor; testes negativos de identidade |
| R03 | R02 | Canal de saída, handshake, limites, heartbeat, journal e operações idempotentes com peers sintéticos em processos separados |
| R04 | R03 | Abertura/eventos/steering/interrupt/close remotos; geração, reconciliação, boot e proteção contra órfãos; não duplicar entregas |
| R05 | R04 | UI de máquinas e destino do endpoint, descoberta MCP/REST, comandos copiáveis, auditoria e documentação operacional |
| R06 | R05 | Matriz completa, campanha A/B/C em configurações aprovadas, build/pacote, rollout gradual e evidência de recuperação |

Em cada milestone registrar SHA real, símbolos/arquivos alterados, comando
exato, resultado, logs sanitizados, limitações e próxima dependência em
`IMPLEMENTATION_STATUS.md` deste diretório. Adicionar backlog executável em
R00 e vincular ao backlog raiz, sem sobrescrever evidência da PR34. Commits e
pushes seguem `feature/v0.2.0`; sem merge automático.

## Matriz mínima de aceite

1. A controla B e C em processos/hosts separados; agente mantém identidade;
   endpoint certo executa uma vez, outro endpoint permanece inativo.
2. Paridade MCP HTTP/stdio e REST, isolamento entre agentes/executores,
   tentativa de spoofing, convite reutilizado/expirado, revogação e rotação.
3. Revogação e mudança de perfil antes do despacho e durante startup;
   sessão antiga não recebe nova autorização por ter estado online antes.
4. Quedas antes/depois da persistência e antes/depois do efeito nativo,
   perda de ACK, reconexão, duplicação, reordenação, lacuna de eventos,
   resultado desconhecido e ausência de replay inseguro.
5. Executor antigo/clone, geração obsoleta, partição longa, relógio divergente,
   reinício do Nexus e executor; sem substituição ou execução dupla incerta.
6. Disco cheio, journal no limite, consumidor lento, payload excessivo,
   capacidade esgotada e cancelamento; sem threads/filas ilimitadas.
7. Múltiplos turnos e capacidades reais de cada conector; sandbox/approvals
   preservados; ambiente e segredos isolados; attach somente em host compatível.
8. Boot, abertura sob demanda, encerramento e ausência de órfãos; conversa
   não ganha permissão de handoff; inbox/outbox preservam suas semânticas.
9. UI com executor offline/revogado/incompatível, fluxo de aprovação,
   comandos copiáveis e descoberta sem exposição de dados alheios.
10. Atualização de instalação existente, compatibilidade de versões,
    migração aditiva, backup/restauração e desativação segura da modalidade.

Fixtures primeiro. Testes reais de Codex/Claude precisam de configuração
isolada explicitamente aprovada nas máquinas de destino; a autorização
histórica para instalações locais não aprova contas/hosts remotos arbitrários.
Pi e attach permanecem NOT_RUN até configuração própria aprovada. Teste
indisponível é NOT_RUN, nunca PASS por herança de resultados anteriores.
O gate final requer a modalidade habilitada segura e utilizável, com cada
limitação de protocolo explicitada e a campanha externa identificada.

## Rollout e recuperação

Começar opt-in para execução remota, preservando os defaults locais atuais.
Vincular endpoints legados ao executor embutido por migração aditiva;
não habilitar destinos remotos automaticamente. Não compartilhar o arquivo
SQLite por rede: A conserva o banco canônico e cada executor seu journal.

Atualizar A e um executor de teste, verificar negociação de versão, então
ampliar. Para interromper rollout, bloquear novas aberturas remotas, drenar
ou reconciliar sessões e revogar credenciais conforme necessário. Preservar
journals e estados incertos. Não executar migração reversa destrutiva nem
instalar writer antigo em schema incompatível. Documentar restauração de
backup e versões compatíveis antes da campanha real.
