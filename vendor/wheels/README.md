# Wheel Core fixado para R4

Current: `nexus_connector_core-0.2.13.dev0-py3-none-any.whl`

SHA-256: `be0d974b036d6384e69655cff5556d6f5ee853f991a913087fe947c56fa2be96`

Este é o mesmo artefato no Nexus, Connector e Core. O `uv.lock` referencia
esta pasta para que `uv sync --extra serve-lite` funcione sem clone irmão.
Este wheel inclui codec R4 `development-partial`, mas o contrato negociável
continua R3; efeitos remotos R4 permanecem fechados. O wheel 0.2.12 permanece
somente para rastreabilidade da versão anterior.
