# Wheel Core fixado para R4

Current: `nexus_connector_core-0.2.14.dev0-py3-none-any.whl`

SHA-256: `759cdee946037ed5e215f901cdfb09b31baf350c7fde69e4d5f79bd41f515bee`

Este é o mesmo artefato no Nexus, Connector e Core. O `uv.lock` referencia
esta pasta para que `uv sync --extra serve-lite` funcione sem clone irmão.
Este wheel inclui codec R4 `development-partial`, mas o contrato negociável
continua R3; efeitos remotos R4 permanecem fechados. O wheel 0.2.12 permanece
somente para rastreabilidade da versão anterior. A versão 0.2.13 também
permanece para rastreabilidade do primeiro preview R4.
