# Installed acceptance audit — October 2, 2026

These findings update the delivery diagnosis, not release-gate status.
The full immutable-input Windows R4 regression is still running while this
record is written. Source, test and plan inputs have not been edited during it.

Follow-up: that run subsequently completed with 708 passed, 6 failed, 2 errors
and 6 skips, with unchanged inputs. Corrections and the OpenAPI fix were then
applied, and a fresh wheel installation passed 26 directed cases in 109.76
seconds with unchanged inputs. See `r4-053-full/` and
`r4-053-installed-corrections/`. The full passing regression remains outstanding.

## Completed evidence

- Connector `4724cc6`: hosted run 36958974449 passed all six Windows/Linux,
  Python 3.11–3.13 test jobs and artifact build. The earlier receipt observation
  failure is superseded by this passing current-revision run, not erased.
  See `connector-4724cc6-ci.json`.
- Core `3a1e884`: hosted run 36961433275 passed all six Windows/Linux,
  Python 3.11–3.13 jobs and SBOM. The two public-documentation failures in the
  prior run were corrected; the executable Core wheel remains unchanged.
  See `core-3a1e884-ci.json`.
- Installed Linux directed R4 campaign: 38 passed, unchanged input hashes.
  See `r4-053-linux-conformance/`. This uses synthetic peers in WSL on the same
  physical host; it does not establish native Linux or independent-host acceptance.

## Confirmed release gaps

The actual installed dashboard still presents legacy connection setup rather
than executor → installation → workspace selection. It duplicates provider
labels and includes Portuguese application text. See `ui-053-inspection.json`.
M10/NS13 and packaged UI acceptance remain incomplete.

The installed OpenAPI endpoint returns HTTP 500 because the postponed return
annotation `FileResponse` cannot resolve its function-local import. An isolated
diagnostic added the import to the module namespace before app construction;
schema generation and authenticated-context HTTP retrieval then succeeded.
No package/source file was changed by that diagnostic. Apply a module-level
import and a packaged-schema regression after the current immutable run ends.
See `openapi-053-diagnostic.json`.

Comparing the corrected diagnostic schema to the normative route table found
two missing HTTP routes, confirmed by a search of the actual HTTP source:

- `POST /v1/runtime/executors/{id}/inventory:refresh`
- `GET /v1/connections/bindings/{id}`

The third schema absence, `/v1/runtime/executors/{id}/link`, is an existing
WebSocket route and is not a missing HTTP endpoint.

The runtime-options implementation also still rejects an operator querying
another agent and always returns false for can_prepare/can_bind/can_start.
The normative contract requires subject-or-operator access, optional workspace
scope and separate effective eligibility decisions. This needs implementation
against the canonical authority services, not frontend authorization rules.

Final artifact freeze, complete Nexus regressions, canonical UI journeys,
native platform/fault matrices and independent-host acceptance remain open.
No M13 or G0–G3 completion is claimed.
