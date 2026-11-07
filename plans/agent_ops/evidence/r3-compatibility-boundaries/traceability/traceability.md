# Revisão finita de rastreabilidade R3

Base: Nexus `5545dbde`, Connector `fb3fff47`, Core `5d317843`. Plano R3 SHA-256 `20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996`; conjuntos 59/132/28/17 preservados. Seguimento público `bcf0e8aa` tratado separadamente. Somente leitura; nenhuma suíte, build, campanha real, credencial ou serviço foi executado/acessado, e nenhum status foi promovido.

Não encontrei defeito adicional de produto ou recurso ausente nos pacotes. Conferi 1.384 entradas de manifests, inclusive sobreposições entre manifests aninhados: zero divergência de hash/tamanho/caminho. As 724 referências locais literais examinadas e 428 caminhos das listas `evidence` existem. As 71 identidades únicas do milestone conjunto apontam a casos aprovados nos XMLs indicados; reruns não foram somados.

| Pacote | Arquivos fonte/wheel | Recursos conferidos |
|---|---:|---|
| Nexus 0.3.3 | 690 | 513 Python, 167 migrações SQL, 7 arquivos UI, 3 outros recursos; bytes iguais também à instalação CI |
| Connector 0.0.12 | 123 | 122 Python e `py.typed`; pin a8cf1810 atual |
| Core 0.0.14 | 165 | 131 Python, 31 schemas JSON, 2 recursos JS e `py.typed`; pin 5721e462 atual |

Nenhum arquivo de recurso fonte ficou fora dos wheels. O solve atual com MCP 1.30/pip check corrige o pin antigo e a insuficiência do ambiente histórico de browser MCP 1.29.1; isso não transforma o browser histórico em prova de solve.

## Mínimo restante

1. **Rastreabilidade por escopo:** RG09 ainda só cita Herdr no baseline. Ligar os drivers/relatórios atuais de mixed, sessões e browser, e os vínculos específicos INV03/05/06/09/11 fornecidos no JSON. Contagem e ausência de link não provam ausência de implementação; nenhuma promoção global é sugerida.
2. **AC10/INV11:** a correção bcf0e8aa removeu dois literais do snapshot público e preservou os resultados. Os oito testes de proteção abaixo já têm aprovações retidas. A validade/revogação da chave UAT histórica segue desconhecida; o histórico Git e o conteúdo visual/binário não foram certificados. Manter esse limite; não reescrever histórico nem usar a chave como parte desta tarefa.
3. **Documento de campanha:** publicar a atualização já preparada pelo root em `plans/agent_ops/campaigns/windows-user-service.md`, que liga a proposta vigente SHA `fbf8644cf836886bc7bac596211a783d6090e79077c643b1d2a627c87a3a37e3`. Seus 24 comandos continuam não autorizados/não executados.
4. **Aceites distintos:** consumir RG07 quando a campanha paralela fechar. Dois clientes reais, harness/provedor real e serviço nativo/login/crash/contexto continuam dependências de campanhas explícitas. TLS/dois hosts só se aplicam ao escopo que for declarado qualificado; não constituem requisito universal novo. Nenhuma repetição ampla de testes é indicada por esta auditoria.

## Isolamento: o que a evidência permite afirmar

Mixed limpa variáveis de aplicação/provedor e fixa profile/appdata/cwd/basetemp temporários antes dos imports; valida origem dos módulos. RG04 retém allowlist do SO e todos os diretórios descartáveis, com Python-I e verificação instalada. São evidências suficientes para essas campanhas sintéticas selecionadas.

Os wrappers RG03/RG05 retêm temp/cache próprios, redigem saída e usam fixtures temporárias, mas herdam o ambiente em vez de reter a mesma allowlist completa de RG04. Não generalizar a prova mais forte para todos 71 casos. Isso é limite da prova de isolamento, não demonstração de alteração pessoal. Campanhas reais futuras precisam de seus próprios limites e fechamento.

## Inventário Herdr resolvido

`collect_artifacts.py` é o driver de fechamento/verificação citado pelo milestone. `initial-manifest.json` é o manifesto histórico de 316 testes/11 relatórios, preservado pelo collector. Ambos estão fora das 142 entradas do manifesto principal por função de proveniência, e ambos já constam com hashes exatos no inventário público `r3-public-artifact-review/scan-after.json`. Não há artefato de runtime perdido nem necessidade de reescrever o manifesto fechado; `supplemental-checks.json` registra a associação.

## Proteções já aprovadas, sem rerun

| Proteção inspecionada | Fonte | Resultado retido suficiente |
|---|---|---|
| Material único fora de resultado/checkpoint/export; recibo com campo secreto recusado; material somente TTY separado do stdout | `tests/execution_r4/test_remote_terminal_setup.py:209,263,308` | `pr03-remote-bootstrap/candidate-v1/nexus/installed.xml`:3 casos |
| Fallback de prompt ecoado interrompido; erro HTTP malformado sanitizado; redirect HTTP real sem encaminhar Bearer | `tests/execution_r4/test_participant_init.py:228,268,279` | `pr04-participant-removal-installed.xml`:4 casos |
| Erro do processo/launcher sem segredo na saída | `tests/execution_r4/test_participant_launch.py:189` | `pr04-participant-removal-installed.xml`:1 caso |
| Origem inválida sanitizada na construção do cliente | `tests/test_observation_client.py:209` | `pr09-herdr/installed/qualified-v2/pr09-observation-installed-v2-initial.xml`:14 casos parametrizados |

São 8 funções / 22 identidades selecionadas, não uma nova execução nem uma certificação universal contra vazamento. `protection-tests.json` contém assertions reais, hashes de função/relatório e todas as aprovações sobrepostas, sem somá-las; parâmetros são representados por digest de identidade. AC04 mantém a avaliação existente apoiada por ações autorizadas no browser/backend; nenhum requisito de provedor real foi acrescentado a esse critério.

Detalhes: `traceability.json` inclui os 17 ACs e 28 invariantes literais, RG08/RG09, limites e referências. `verification.json`, `payload-verification.json` e `supplemental-checks.json` retêm os resultados verificáveis. Esta revisão não substitui o aceite global R3.

Recomendação literal ao root: a prova atual é suficiente para RG-08. AC-07 também é atendido pelo solve/pins/fronteiras atuais e pelo RG-06 em fechamento separado; não depende de campanhas de provedor. AC-09 pode ser concluído como declaração honesta do snapshot ao reter o inventário nomeado NOT_RUN e seus limites, sem exigir que esses testes sejam executados. A decisão e qualquer atualização do ledger pertencem ao root.
