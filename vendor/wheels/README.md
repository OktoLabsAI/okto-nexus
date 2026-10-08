# Current release dependency

Core 0.0.5 is required by Nexus 0.2.2 and Connector 0.0.4.
The shared wheel SHA-256 is `71acdfc06102ee549b3f46106017e19f63d6d00ce2ede0243f91fffd34af4d3f`.
It includes the Pi startup containment correction from Core commit `861d191`.
The entries below document historical artifacts.

Current PyPI release candidate: `okto_nexus_connector_core-0.0.1-py3-none-any.whl`
SHA-256: 1547d389913f6de6b9060f03b9492b38be660d876ab1d6a5298442720cf28421.
Python imports remain `nexus_connector_core`.

## Current development artifact: 0.2.53.dev0

nexus_connector_core-0.2.53.dev0-py3-none-any.whl

SHA-256: cc873031378793d374a9bbc00572c7a525f99c4246324a941713d866cc62c6b1

Executable R4 contract with an explicit revision identity; historical R3 bytes
remain unchanged. Provider and final release acceptance remain separate.

## Previous development artifact: 0.2.52.dev0

nexus_connector_core-0.2.52.dev0-py3-none-any.whl

SHA-256: 470eb23b28d917a3a154c2ef7cd9fdddf972ca6402c0668961b4c01909f1b732

Lease limits compare absolute deadlines, accepting the exact maximum without floating-point subtraction drift. The next representable deadline remains rejected before native effects. Both consumers use identical bytes; final release gates remain open.

Earlier entries below describe historical artifacts, not the current dependency.

## Previous development artifact: 0.2.51.dev0

nexus_connector_core-0.2.51.dev0-py3-none-any.whl

SHA-256: 4c4c0c58d25b93f4f08ba8515d8476ffc29d1f0a27cc577c9fccb610716d1d1c

Lost R4 revocation acknowledgements recover only from the exact durable fence row, without another CAS. Mismatched rows do not authorize an ACK or native work. Release gates remain open.

## Previous development artifact: 0.2.50.dev0

nexus_connector_core-0.2.50.dev0-py3-none-any.whl

SHA-256: 797e28d34ba43800e5ad800b0fb344ce53a4160389ac817b4687505187c25215

Public memory-only shutdown_resources distinguishes observed STOPPED from pending durable release. It does not authorize disposal or replace shutdown outcomes. R4 release gates remain open.

## Previous development artifact: 0.2.44.dev0

nexus_connector_core-0.2.44.dev0-py3-none-any.whl, SHA-256
c6f8555adeadb68959daa8e2ad91ec755eab49183049112a3d719470321e8db0.

Bounded file-read allocations preserve the complete Pi build identity and size-change refusals.
The same wheel is used by Nexus and Connector; release gates remain open.

## Previous development artifact: 0.2.35.dev0

nexus_connector_core-0.2.35.dev0-py3-none-any.whl, SHA-256
20013ae173652ea3726f5b7ae5d7c37e66eac8f9bc319ae3c36f84e70247e760.

Retained policy-close receipt completion.

## Previous development artifact: 0.2.33.dev0

nexus_connector_core-0.2.33.dev0-py3-none-any.whl, SHA-256
1f119d5626e9de4c8dc2589b0941289d300e995b6a422ebc16b627be5b61fee1.

Durable R4 terminal close receipts.

## Previous development artifact: 0.2.32.dev0

nexus_connector_core-0.2.32.dev0-py3-none-any.whl, SHA-256
a32d49400c0e22ccedd1fbe7f26b8f74ff0b3bb2d55f21eac469dd0ae8a8784f.

Confirmed native close outcomes.

## Previous development artifact: 0.2.31.dev0

nexus_connector_core-0.2.31.dev0-py3-none-any.whl, SHA-256
6e3e6e08acee45c8c220bb87d8f79b9697cc95c177b73f37414aa601880d6339.

Exact Windows Codex 0.159.0 conversation and control qualification.

## Previous development artifact: 0.2.30.dev0

nexus_connector_core-0.2.30.dev0-py3-none-any.whl, SHA-256
e060e033be05fdd4c9aff5c90902d191483d400b3f6778fa7bb5395b66f561e6.
The same bytes are used by Nexus and Connector. Pi native action ingress
retains backend producers through timeout and shutdown. Both hosts compose
the public Pi launch owner and retain stores while native domain work remains
pending. Automatic approved configuration and real provider acceptance remain
pending; R4 readiness remains false.

## Historical development artifact: 0.2.29.dev0

`nexus_connector_core-0.2.29.dev0-py3-none-any.whl`, SHA-256
`a465c1ec1aaba9814872b21984a436bbf4cac5f28c2b4bed776f1a7042426cba`.
The same wheel is used by Nexus and Connector. Native domain capabilities
are fenced by the current installed R4 session authority, independently of
the seven runtime operations. Host lifecycle integration and provider
qualification remain pending. R4 execution readiness remains false.

# Wheel Core fixado para R4

Current: `nexus_connector_core-0.2.14.dev0-py3-none-any.whl`

SHA-256: `759cdee946037ed5e215f901cdfb09b31baf350c7fde69e4d5f79bd41f515bee`

Este Ã© o mesmo artefato no Nexus, Connector e Core. O `uv.lock` referencia
esta pasta para que `uv sync --extra serve-lite` funcione sem clone irmÃ£o.
Este wheel inclui codec R4 `development-partial`, mas o contrato negociÃ¡vel
continua R3; efeitos remotos R4 permanecem fechados. O wheel 0.2.12 permanece
somente para rastreabilidade da versÃ£o anterior. A versÃ£o 0.2.13 tambÃ©m
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
