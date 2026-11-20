# Atualização de uma base anterior às sessões interativas

Os wheels do baseline do plano, Nexus 0.3.7, Connector 0.0.13 e Core 0.0.14, foram reconstruídos dos SHAs exatos e instalados em um ambiente isolado. O teste `test_public_operation_history_returns_canonical_output` do baseline gravou uma abertura, um turno com resultado determinístico e um fechamento usando o fluxo canônico. O candidato usou Nexus 0.3.8, Connector 0.0.15 e Core 0.0.16. [Versões, SHAs e resultados](si039-pre-interaction-upgrade.json)

O comando instalado `okto-nexus admin backup` criou o backup da base no esquema 168. Em uma cópia desse backup, o migrador instalado aplicou as 19 migrações até o esquema 187. Uma segunda execução aplicou zero migrações. A comparação das colunas existentes verificou todas as 90 linhas das 161 tabelas anteriores, excluindo apenas o catálogo de migrações. O Core atual validou os hashes e interpretou os quatro recibos canônicos. Os novos campos de evidência de lançamento e retomada são opcionais e ficaram nulos na sessão antiga. As verificações de integridade e chaves estrangeiras passaram.

A consulta autenticada na API retornou os mesmos três documentos de histórico antes e depois do upgrade, incluindo o resultado do turno. A consulta sem autenticação retornou HTTP 401 nas duas versões. Em uma terceira cópia, o Nexus 0.3.7 abriu o esquema 168 restaurado e retornou o mesmo histórico. A base original e o backup conservaram seus hashes.

Passaram o teste do pacote anterior e 32 regressões com o candidato instalado, incluindo migração, backup, projeção de resultados, fila e recuperação de recibos. O ensaio usa um peer determinístico na criação da base e cobre integração e pacote em Windows. A fase de campanha de SI-T-I01 segue pendente.

Este marco acrescenta evidência, sem alterar o código, o esquema distribuído ou os pins. Para restaurar a base usada no ensaio, reutilize uma cópia do backup pré-migração com os wheels anteriores.
