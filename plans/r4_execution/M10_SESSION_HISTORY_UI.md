# Selected-session event history — 2026-10-02

Runtime operations now shows the selected operation's session history through
the existing canonical events endpoint. Pages hold at most 100 events; previous,
next and refresh are read-only. Session/executor scope, stream epoch, contiguous
sequence and returned cursor are verified before replacing the displayed page.
Changing sessions unmounts and aborts the old reader. Errors preserve the last
successful page with an explicit stale-data warning. A pending gap is visibly
incomplete. Payloads expand on demand; no event payload is saved to tab storage.

Reload recovers the selected operation using its existing durable metadata and
reads the first history page. This is not an all-session catalogue, stream-epoch
selector or an uncertain-runtime repair workflow. Those broader M10 journeys
remain open, along with actual remote/provider browser and accessibility matrix
acceptance. Native macOS, independent hosts, final M13 freeze and G0–G3 remain open.

## Installed evidence

`evidence/session-history-ui-final/`: seven passes in 58.76 s on Windows/Python
3.13.1 and headless Edge; PASS, exit code 0, `changed_inputs=[]`. This covers a
103-event browser replay, next/previous pages, missing-event warning, reload
without POST/new runtime, rejection of foreign scope, existing runtime action
cycle, four canonical event API cases and NS15.05. Browser requests reach the
real installed HTTP application and SQLite; native peers remain synthetic.
The final screenshot was visually reviewed and retained in
`evidence/session-history-ui-final-screenshots/`.

Wheel SHA-256: `74c549b93a9c7b312ddad19c2642ff3bd4edfc7d7b95eb2fae832766b8502cf5`.
Sdist: `778f488496b07ddb39797a23b370e8474f76252c2172dfd8edd902e3f37764be`.
Build used isolated source and fresh TypeScript/Vite output, preserving existing
user static assets. Core .56 and Connector wheel hashes remain
`7f19885f28b16dbfce66b969ab42c79b9947246416c71147315006b6e618b1f6` and
`93d78a75c5ad81bbdd96e648be136f0f6b2cfd0a53f350266a1c9f96fc449104`.

Earlier `session-history-ui-installed/` (six passes, 56.56 s) and
`session-history-ui-reviewed/` (one pass, 12.24 s) used wheel
`3c143da2a7c5c3d280169ce76a780aa3ff7d3f83a68ab21f2450091e05e8590a`.
Visual inspection then exposed an absent native event label: the UI incorrectly
read `event_type` instead of `native_type`. The final wheel corrects this and the
browser test now explicitly asserts the native label. Original evidence remains.

Reproduce with the reviewed wheel installed, `OKTO_NEXUS_UI_CAMPAIGN=1` and
`OKTO_NEXUS_UI_INSTALLED=1`, invoking the installed interpreter with
`tools/ci_installed.py test --wheel <wheel> --output <fresh-directory> --tests`
and the test selection recorded in the final campaign JSON. Actual Pi acceptance
on the preceding wheel remains separate evidence, not a run on this UI wheel.
