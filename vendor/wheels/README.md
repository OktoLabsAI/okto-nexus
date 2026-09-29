# Wheel Core fixado para R4

Current: `nexus_connector_core-0.2.14.dev0-py3-none-any.whl`

SHA-256: `759cdee946037ed5e215f901cdfb09b31baf350c7fde69e4d5f79bd41f515bee`

Este é o mesmo artefato no Nexus, Connector e Core. O `uv.lock` referencia
esta pasta para que `uv sync --extra serve-lite` funcione sem clone irmão.
Este wheel inclui codec R4 `development-partial`, mas o contrato negociável
continua R3; efeitos remotos R4 permanecem fechados. O wheel 0.2.12 permanece
somente para rastreabilidade da versão anterior. A versão 0.2.13 também
permanece para rastreabilidade do primeiro preview R4.

Current pinned artifact: `nexus_connector_core-0.2.18.dev0-py3-none-any.whl`,
SHA-256 `547ab7dfde09adff79f38f5cdf688e5b9d0d7ed3caddf4de445766afdefde0da`.
The Core now verifies projection of a native turn receipt into the separate R4
wire hash domain. Remote R4 execution remains disabled.

Current pinned artifact: `nexus_connector_core-0.2.19.dev0-py3-none-any.whl`,
SHA-256 `3b1b334f61f8ad5a2a59c63dcd127ced26a9d426dde7bff68085e4081d01c072`.
Projection failures after a Core receipt preserve possible effect and refuse
safe retry. Remote R4 execution remains disabled.
