# Entrega ao agente executor do Nexus Server

## Arquivos e ordem de leitura

Leia `01_ARQUITETURA_E_PLANO_MESTRE.md`, `02_CONTRATOS_HTTP_NXL_E_ESTADOS.md`, `03_DADOS_MIGRACAO_E_RECUPERACAO.md` e `04_BACKLOG_EXECUCAO.md`. Use `05_TESTES_E_ACEITE.md` e os JSONs como estado atualizável. `06_HANDOFF_CORE_CONNECTOR.md` fixa dependências externas; `07_RASTREABILIDADE_R3.md` conserva o escopo original. `08_FONTES_BASELINE_E_DECISOES.md` distingue inspeção de especificação.

`PLANO_COMPLETO_NEXUS_SERVER_R4.md` é uma concatenação de leitura gerada dos documentos, não outro plano a editar independentemente. Os arquivos em `contratos/` são **propostas normativas e fixtures de planejamento**, não contratos já publicados pelo Core. A fonte executável de produção deve ser o bundle Core R4 acordado.

## Prompt pronto

```text
Implemente a reestruturação do Nexus Server definida neste pacote R4.
Trabalhe em OktoLabsAI/okto-nexus, branch feature/v0.2.0. O baseline
verificado foi 7ed52c22865a92c3768bc32508ed9e35dc5efdc3; registre o HEAD
atual e preserve alterações posteriores. Não faça reset --hard/clean.

Leia integralmente 01, 02, 03 e 04. Execute NS00 primeiro. Use o backlog
BACKLOG_R4.json (17 fases, 85 tarefas), atualizando estado e evidência por
ID. A matriz tem 164 cenários de produto ainda NOT_RUN, incluindo os 79
TN/J preservados. Os comandos de testes novos são alvos a implementar.

Regras fechadas:
- identidade canônica é do agente; nenhuma conta de usuário Nexus nova;
- MCP somente HTTP direto no Server, sem stdio/shim/proxy no produto;
- Server local usa Core embutido, sem app Connector e sem WSS local;
- runtimes/catálogo/qualificação/refs de instalação vêm do Core;
- Server não resolve paths remotos nem instala providers;
- /v1 novo retorna objetos diretos; /api/v1 legado é preservado;
- resolve não executa; POST operations admite; receipt nunca executa;
- todo efeito produtivo é despachado pelo Server uma vez, inclusive
  comandos originados da CLI Connector;
- aprovação canônica gera UMA operação de aplicação; nenhuma segunda
  aplicação pela CLI ou pela notificação;
- snapshot do executor e seleção usam candidato completo/ref/revisão;
- cancelamento da espera não abandona producer/ownership/commit;
- unknown mantém supervisão; não anunciar pronto por write no socket.

Core de referência: 0.2.10.dev0, SHA 1560d314ed2b478515dcbbe533436d7d0b027b09.
Connector de referência: 0.4.0.dev0, SHA 87b8fd2e3e403cb6a70a1ce265618e29c7a6b86c.
NXL R4 deste pacote ainda requer publicação no Core e adoção pelo Connector.
Abra CORE-R4/CON-R4 conforme 06; não implemente outra cópia dos contratos
ou adapters para evitar essa dependência. Continue partes independentes
com fixtures; não habilite efeito remoto antes do gate compartilhado.

Para cada tarefa: altere os símbolos indicados; cumpra todos os passos;
crie os testes descritos; execute e registre comando/exit/XML/log/hash;
compare positivo e negativo; marque DONE só com prova da camada correta.
Não substitua implementação por novo plano. Não decida campos, rotas,
retries, nomes de estado ou permissões por inferência: siga 02 e 03.
Conflito com o HEAD exige registro objetivo e ajuste de crosswalk, não
mudança silenciosa de semântica. Falta externa fica BLOCKED_EXTERNAL.

Não publique/push/release, use credenciais reais ou modifique hosts de
produção sem autorização específica. Não declare G2 por peers sintéticos.
Entregue código, migrações, contratos por hash, artefatos, testes, decisões,
limites e as pendências por responsável.
```

## Verificação do pacote de planejamento

```bash
python validar_pacote.py
```

Este comando valida documentos/backlog/schemas/fixtures. Não testa o Nexus nem substitui a suíte do produto. Não instala dependências; exige `jsonschema` para a parte de schema. Tarefas começam PENDING, produto NOT_RUN.

## Execução distribuída entre agentes

O agente do Core produz o contrato antes da integração real; o agente Connector conclui CN5 e adota R4; o Server avança em paralelo. Não bloquear desenvolvimento esperando que outro repo se declare totalmente DONE. Não fechar uma capacidade cujo contrato ainda não permite a operação correspondente.
