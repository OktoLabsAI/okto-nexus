# SI-018 ownership observation in Nexus and Connector

Nexus and Connector now use the same Core 0.0.16 wheel from `30f349b293fd8d4458dee0267c04aaf3eda132af`. Connector 0.0.15 is on `feature/v0.0.15` at `9283c0af08ac288123165111e19df6e9dd74808b`. Nexus updates its exact inventory pin and CI manifest with both matching wheel hashes.

Both hosts resolve the existing runtime from their exact in-memory registry, pass the full R4 scope and expected native target to Core, and confirm that the runtime is still registered when the proof returns. Missing and stale registrations fail closed. The path opens no runtime and grants no terminal write authority. It remains internal to the host until the presenter and capability flow is complete.

## Evidence and rollback

- With installed Core 0.0.16, Nexus passed 99 session interaction and dispatch tests plus 8 inventory cases. The R4 synthetic fixture joins the retained Server mapping to the live Core proof and checks foreign Server and owner generation refusal.
- Connector passed 106 tests with one existing platform skip. Its synthetic R4 scenario verifies the exact existing runtime, rejects a sibling executor and stale generation, and rejects a deregistration that happens during the proof. A baseline structural test already omitted the daemon's bounded supervisor from its allowlist. The test now recognizes that existing service launcher. The supervisor implementation and its tests of retry and lifecycle behavior continue to run.
- Both consumer archives passed strict Twine checks. The three wheels installed into an isolated target directory. The two proof integration cases also passed against those installed Nexus and Connector packages. The Nexus lock and vendored CI hashes were checked offline.

No database migration or R4 wire change is involved. Rollback of consumer integration restores the prior pins and the matching CI manifest together. SI-018 remains in progress for qualified build revalidation at attach, an authenticated presenter, and live handoff and transfer evidence.
