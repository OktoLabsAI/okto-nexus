# P02/P11 — fifth adapter in the actual five-adapter composition

Parent `605557a`, feature/v0.2.0, 2026-09-23. Test-fixture/evidence improvement;
no production contract or schema change. Final gate NOT PASSED.

Inspection found that the existing additional-adapter integration fixture replaced
the registry with only its fifth entry. It exercised the production facade but did
not prove coexistence with the four preserved connectors. The strengthened catalog
assertion reproduced this gap: expected five IDs, observed only fixture.additional.v1.

The fixture now obtains the production registry through build_connector_factories
and adds one trusted version1 descriptor. It creates all five approved endpoints
and the applicable profiles through REST. MCP and REST catalogs must expose the
same five entries. Parameterized paths open the extension through authenticated
MCP and exercise both administrative REST send and authenticated canonical message
delivery. The latter proves the exact operation/message/sender/recipient envelope,
selected endpoint and exclusive unread inbox reservation.

The fifth adapter is processless: a scoped Popen trap fails the test if open/send
tries spawning a native process. It still uses a logical HarnessSession for Nexus
tracking; this is not a claim that every endpoint lacks session state. The fake
implements the existing port and receives canonical envelopes directly. No new
domain enum, supervisor product branch, broker or real A2A implementation was added.

Files/symbols: tests/test_pr34_remediation.py runtime fixture and
test_p02_additional_adapter_through_production_mcp_and_rest. Existing four connector
factories and capability descriptors are retained rather than copied or replaced.

## Commands/results

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_pr34_remediation.py -k p02_additional`:
  initial **RED**,1 FAIL/35 deselected,3.74s: four original catalog entries absent.
- First fixture correction/expanded assertions:2 FAIL/35 deselected,6.01s because
  the assertion read a nonexistent public FakeConnector.kind attribute. It now
  verifies the actual open response kind. No production change was needed.
- Same selection after correction: **2 PASS**,35 deselected,7.51s. Both paths
  prove no local process spawn. No real provider or personal session was used.
- `rtk proxy ruff check tests/test_pr34_remediation.py`: **PASS**.

T-ENDP-08 is covered by this processless extension composition. Effective installed
binary probes (T-ENDP-07) remain separate and pending. No native connector campaign
is inferred from this fake; Pi/Claude attach native remain NOT_RUN.

Expanded selections:

- `rtk proxy .venv/Scripts/python.exe -m pytest -q tests/test_pr34_remediation.py tests/test_runtime_contracts.py`: **48 PASS**,66.59s.
- `rtk proxy wsl -d Ubuntu --cd /mnt/d/Projetos/Techridy/okto_labs_okto_nexus -- /var/tmp/okto-pr34-native-python-q84f5fav/venv/bin/python -m pytest -q tests/test_pr34_remediation.py tests/test_runtime_contracts.py -k "additional or registry"`: **4 PASS**,44 deselected,12.13s.
