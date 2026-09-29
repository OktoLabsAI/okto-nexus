# Contratos de planejamento, não codecs publicados

`http-target.schema.json` contém DTOs de forma fechada para implementação coordenada. O schema não substitui autenticação, comparação entre campos, canonicalização/hash, quotas em bytes, autorização, estado da sessão ou validadores nativos do Core. As propostas nativas são delegadas ao contrato próprio do Core, não reinterpretadas neste schema.

`http-routes.json` identifica as 23 rotas e referências aos DTOs. O upgrade WSS usa os schemas NXL R4 que deverão ser gerados no Core. `nxl-r4-delta.json` é a instrução para essa evolução, não um segundo codec no Server. Todos são alvos ainda não implementados.

`fixtures-planejamento.json` traz 16 verificações de forma (seis positivas e dez negativas). Os hashes são placeholders sintaticamente válidos; não são vetores JCS nem credenciais. O validador documental não executa nenhum produto. O Core deverá gerar vetores reais de hash, mensagens de protocolo e testar o código do Server/Connector.

A inspeção de uma definição JSON não comprova invariantes relacionais: por exemplo, server_id do corpo precisa coincidir com a origem autenticada, hashes precisam corresponder ao conteúdo e a mesma candidate_ref continua escopada ao executor. Esses requisitos estão nos documentos01–03 e na matriz de produto.
