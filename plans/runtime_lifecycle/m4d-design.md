# M4d — Retirar o histórico do caminho de admissão

Plano em implementação. O checkpoint M4d1 está descrito em `m4d1-validation.md`;
a retirada completa do histórico do caminho de admissão permanece pendente.

No M4c, a inicialização ainda carregava todas as sessões, enumerava o diretório
e aplicava o limite de 32.768 registros, apesar de não reabrir journals já
verificados. O M4d1 substitui o mapa completo de sessões pelo catálogo canônico
e por buscas exatas de reservas; a enumeração inicial de arquivos e os tetos
dos caminhos de recuperação por agente continuam pendentes.

Antes de introduzir outro índice persistente, comparar duas opções no código:
manter os journals por sessão com catálogo durável, ou adotar um journal por host
com escopos de sessão, como o Connector já faz. A segunda opção pode eliminar
catálogo de arquivos e duplicação de recuperação, mas exige demonstrar isolamento
de falhas, limites de armazenamento e migração retomável das evidências existentes.
Não escolher somente pela redução do número de arquivos. Registrar a decisão
antes da mudança de armazenamento e coordená-la com M5.

Decisão inicial registrada no M4d1: preservar journals por sessão e acrescentar
somente a localização derivada à sessão canônica. Isso não altera o protocolo
Core nem cria um segundo ledger. A adoção de armazenamento físico compartilhado
não foi qualificada; M5 mantém a unificação das políticas pelos adaptadores.

## Ordem de implementação

1. Substituir o mapa histórico usado para atribuir reservas ocupadas por buscas
   exatas de sessão/abertura. Reservas provisórias continuam exigindo a associação
   durável do Core; não aceitar identidade inferida pelo nome de arquivo.
2. Descobrir agentes com pendências pelos índices duráveis, em lotes e com cursor.
   Um agente sem pendências não deve esperar pela leitura de journals de outro.
   Uma sessão sem stream precisa de prova própria de não execução ou recusa;
   nunca receber automaticamente o checkpoint de uma sessão executada.
3. Tornar a primeira auditoria do armazenamento retomável. Antes de tirar a
   enumeração de arquivos do caminho obrigatório, estabelecer um catálogo durável
   no dono do armazenamento: registrar a intenção de criar o journal antes de
   permitir admissão nativa e validar as reservas ocupadas na retomada. Um catálogo
   incompleto ou contraditório não pode ser tratado como ausência de processos.
4. Separar a auditoria histórica do controle de sessões atuais depois de uma
   primeira auditoria comprovada. Manter erros atribuíveis isolados por sessão ou
   agente; erros de autoridade compartilhada continuam bloqueando o host.
5. Aplicar orçamento e cursor à recuperação/publicação. Um stream continuamente
   ativo não pode monopolizar o trabalhador do agente; preservar o cursor apenas
   depois do commit e confirmar eventos somente depois de persistidos.

## Evidências exigidas

- Mesmas pendências com 1k/10k/100k sessões encerradas: medir consultas, journals
  abertos e trabalho de startup, distinguindo primeiro backfill de boots seguintes.
- Interromper e retomar entre registro do catálogo, criação do journal, reserva,
  prova e checkpoint. Nenhuma admissão duplicada ou liberação sem prova.
- Reserva ocupada sem correspondência, catálogo ausente/corrompido e journal
  inesperado: diagnóstico explícito, sem descarte de evidências.
- Dois agentes independentes, um journal travado; controlar o progresso do outro.
- Dois streams do mesmo agente, um com eventos contínuos/grandes; ambos avançam,
  inclusive sob falha temporária de commit, sem ACK antecipado.

Mudanças no catálogo do Core exigem atualização coordenada do Nexus e Connector
e teste diferencial no M5. A remoção da enumeração não precede essa garantia de
propriedade. A arquitetura do supervisor continua sendo uma decisão separada no M6.
