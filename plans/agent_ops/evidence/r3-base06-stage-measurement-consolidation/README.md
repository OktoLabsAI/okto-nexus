# BASE-06: consolidated actual stage measurements

The fixed plan (245/247) asks for measured stages and the complete terminal route. It does not require a clean stopwatch or a homogeneous package across the whole development history. Existing measurements remain valid within their labelled scopes.

| Stage | Seconds | Clock / scope |
|---|---:|---|
| v12 product wheels installation | 12.9945733 | Monotonic; excludes dependencies/download/build |
| v12 installation plus verification | 58.1911667 | Same installer; includes payload/import/pip checks |
| W17 service registration | 10.7141757 | Recorded wall endpoints, wrapper overhead included |
| W17 service start | 37.3520083 | Recorded wall endpoints |
| W17 authorization review | 13.9927521 | Recorded wall endpoints |
| W17 authorization apply | 13.4243622 | Recorded wall endpoints |
| W17 useful15 execution through validated report | 148.2299977 | Same-process monotonic |
| W17 useful wrapper | 153.9653945 | Wall endpoints, includes wrapper overhead |
| W17 continuation wrapper | 24.2673459 | Wall endpoints; real same-session response |

The historical installation-to-useful wall span includes debugging, package updates and human waits; these are part of that observed trajectory, not reasons to discard every stage. Do not add stages from different package scopes into an unlabelled benchmark. W16/R package-install clocks remain unknown; service registration is not pip installation. Exact derived intervals and source pins are in review.json/timing-projection.json.

Local measured first use is established in its scope. Remote onboarding and failed paid attempts are real, but no remote useful report and complete corresponding continuation have been confirmed. BASE-06 remains IMPLEMENTED for that literal remaining route; no new clean/homogeneous timing requirement or paid/local rerun is introduced. The old baseline is retained as historical; no scenario, AC, budget or fixed plan is changed.
