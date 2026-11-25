# SI-039 · Pacote instalado, migrações e clientes anteriores

A suíte do pacote anterior encontrou oito falhas ao retomar a migração de catálogo depois de uma adoção aprovada. A inicialização e o encerramento do executor, assim como a adoção, avançavam registros derivados de Attention e o comparador tratava esse avanço como alteração da origem. O comparador agora aceita o avanço somente para os registros correspondentes ao executor ou ao endpoint adotado, com o estado esperado e um epoch maior. A retomada ainda recusa registros ausentes, estados inconsistentes e alterações em registros de Attention fora desse conjunto. [Versões, hashes e resultados](si039-current-package-legacy-upgrade.json)

O wheel e o sdist do Nexus foram reconstruídos offline a partir da árvore revisada e passaram no Twine. Os 818 arquivos de runtime coincidiram entre a árvore, o sdist, o wheel e a instalação. O único arquivo de runtime alterado em relação ao candidato anterior foi o comparador da migração. O dashboard e o OpenAPI foram servidos pelo pacote instalado. Os pins do Connector 0.0.15 e do Core 0.0.16 foram conferidos com os respectivos repositórios e mantiveram os mesmos hashes.

| Cópia histórica | Resultado com o esquema 191 |
| --- | --- |
| Esquema 168 do Nexus 0.3.7 | Preservou 90 linhas, quatro recibos e as três consultas de histórico da API. Outra cópia do backup abriu no Nexus 0.3.7 e mostrou o mesmo histórico. |
| Esquema 188 com retomadas salvas | Preservou as duas provas salvas e oito recibos, com as linhas e os hashes originais. |
| Dois bancos no esquema 190 | A migração preservou os recibos e as operações. O envio incerto ficou em `DELIVERY_UNKNOWN`. O envio com confirmação durável ficou em `ACCEPTED_NATIVE`. A entrada seguinte manteve seu estado. |

Os quatro bancos passaram na verificação de integridade e de chaves estrangeiras. Aplicar novamente o migrador produziu zero alterações de esquema. O CLI atual listou a sessão no Nexus 0.3.7 e informou quando apresentação ou envio de sessão estavam indisponíveis. O Connector 0.0.13 integrou-se ao servidor compatível e respondeu `VERSION_INCOMPATIBLE` ao consultar o Nexus atual, antes de usar credenciais ou registrar um executor.

Passaram 68 testes de migração e recibos, 88 de contratos e dashboard empacotado e os dois ensaios entre versões instaladas. Os 11 testes de retomada no checkout também passaram. Os cenários SI-T-I01, SI-T-I02, SI-T-I05 e SI-T-I06 preservam o estado `NOT_RUN` para as campanhas exigidas.

A correção dispensa migração nova. Para revertê-la dentro do esquema 191, reverta o comparador e reinstale o wheel anterior. A restauração para o Nexus 0.3.7 no ensaio usou uma cópia do backup no esquema 168. A próxima etapa é SI-040, documentação de comandos e capacidade efetiva.
