## Current development artifact: 0.2.29.dev0

`nexus_connector_core-0.2.29.dev0-py3-none-any.whl`, SHA-256
`a465c1ec1aaba9814872b21984a436bbf4cac5f28c2b4bed776f1a7042426cba`.
The same wheel is used by Nexus and Connector. Native domain capabilities
are fenced by the current installed R4 session authority, independently of
the seven runtime operations. Host lifecycle integration and provider
qualification remain pending. R4 execution readiness remains false.

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

Current pinned artifact: `nexus_connector_core-0.2.20.dev0-py3-none-any.whl`,
SHA-256 `7e9addcb72c52aefe35ea136b4c706721b104f6f9ce4a804a0071d2e829ec4c1`.
Steer receipts now have a verified Core-to-R4 projection. Remote R4 execution
remains disabled.

Current pinned artifact: `nexus_connector_core-0.2.21.dev0-py3-none-any.whl`,
SHA-256 `6cf55425acc44b4ead9bfd1abd6e216d2c9ed00c7e137d76800b1a42f2f065ed`.
Verified projections now cover submit, steer, interrupt and close receipts.
Remote R4 execution remains disabled.
