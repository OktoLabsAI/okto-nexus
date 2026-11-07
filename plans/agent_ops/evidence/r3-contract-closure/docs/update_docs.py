"""Apply only the finite, reviewed AC08 documentation corrections."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).parent
ROOTS = {'nexus': Path('D:/Projetos/Techridy/okto_labs_okto_nexus'),
         'connector': Path('D:/Projetos/Techridy/okto-nexus-connector'),
         'core': Path('D:/Projetos/Techridy/okto-nexus-connector-core')}
CHANGES = [
('nexus','docs/service-lifecycle.md',
 'below. General definition reconciliation, upgrade workflows and other-platform\nadapters remain open R3 requirements.',
 'below. Reviewed environment upgrades and owned-task enablement are described\nbelow. Unrelated external definition edits remain refused; actual native service\nand other-platform qualification remain separate.'),
('nexus','docs/terminal-connect.md',
 'runtime policy and harness configuration. Participant initialization,\nnew remote identity bootstrap and real provider\nqualification remain in progress. Reconnect and repeated Finish do not re-enable a policy',
 'runtime policy and harness configuration. Existing-client initialization uses\nthe [participant flow](terminal-participant.md); new remote project identities use\n[remote project setup](remote-project-setup.md). Their implemented setup contracts\ndo not establish real-provider qualification. Reconnect and repeated Finish do not re-enable a policy'),
('nexus','docs/terminal-work.md',
 'for an already approved binding on a remote Server. Unified Connector onboarding\nand its full productive campaign remain unfinished. Native decisions require the',
 'for an already approved binding on a remote Server. To create a remote project\nconnection, use the implemented [Connector onboarding flow](remote-project-setup.md).\nIts real-provider productive campaign remains separately pending. Native decisions require the'),
('nexus','docs/terminal-work.md',
 'and reports native delivery refusal when disabled. Start-at-login review and\nproductive real provider/context qualification remain required before M1 is complete.',
 'and reports native delivery refusal when disabled. Native user-login campaigns\nand productive real-provider/context qualification remain separately pending.'),
('nexus','docs/attention.md',
 'with a successful zero count. The PR-07 client must implement these behaviors.',
 'with a successful zero count. The dashboard uses these reconciliation rules.'),
('connector','docs/service-lifecycle.md',
 'qualified by these Windows results. General definition reconciliation, upgrades and\nreal remote/provider/login/logout campaigns remain in progress. Exact evidence',
 'qualified by these Windows results. Reviewed environment upgrades and owned-task\nenablement are described below; unrelated external definition edits remain refused.\nReal remote/provider/login/logout campaigns remain separately pending. Exact evidence'),
('connector','docs/cli.md',
 'Run okto-nexus-connector reconnect to gracefully stop and restart the daemon for the selected state directory. Configurations and credentials are preserved. Active harness executions may be interrupted during shutdown. The command returns when the daemon is ready; server connections complete asynchronously. Check okto-nexus-connector status and okto-nexus-connector logs --errors for progress. If shutdown cannot finish within 30 seconds, no second daemon is started.',
 'Run `okto-nexus-connector reconnect` to drain and restart the daemon for the selected\nstate directory. Configurations and credentials are preserved. It waits for admitted\nwork and does not request force or interrupt active work when the wait expires.\nIf drain remains pending after 30 seconds, no second daemon is started. Inspect\n`daemon status` and use the [explicit force decision](service-lifecycle.md#drain-and-an-explicit-force-decision)\nonly when intended. The command returns when the daemon is ready; Server connections\ncomplete asynchronously. Check `okto-nexus-connector status` and\n`okto-nexus-connector logs --errors` for progress.'),
('core','docs/api.md',
 '`checkpoint_wal`, `inspect`, `claimed_sessions`, `process_birth`,',
 '`checkpoint_wal`, `inspect`, `claimed_sessions`, `drain_status`, `process_birth`,'),
('core','docs/api.md',
 'successful generation or revocation update; a busy error leaves that update\nunapplied.',
 'successful generation or revocation update; a busy error leaves that update\nunapplied.\n\n`begin_drain()` and `drain_revision()` are synchronous owner-loop methods. The\nfirst fences new productive admission without interrupting admitted work; the\nsecond returns the current activity revision without I/O. `await drain_status()`\nreturns bounded `state`, `quiescent`, `resources`, `activity_revision` and\n`owned_sessions` metadata. Missing or incomplete evidence remains `UNKNOWN`.\nThe exported `combine_drain_status(reports)` helper is only for owners sharing\none journal; the host rechecks every revision after awaits. Independent journals\nmust not be combined. See [cooperative service drain](lifecycle.md#cooperative-service-drain)\nfor ownership retention and the separate explicit containment decision.'),
]

original = {}
for repo, relative, old, new in CHANGES:
    path = ROOTS[repo] / relative
    key = repo + '/' + relative
    raw = path.read_bytes()
    original.setdefault(key, raw)
    newline = b'\r\n' if b'\r\n' in raw else b'\n'
    old_bytes = old.encode().replace(b'\n', newline)
    new_bytes = new.encode().replace(b'\n', newline)
    assert raw.count(old_bytes) == 1, key
    path.write_bytes(raw.replace(old_bytes, new_bytes))

key = 'connector/docs/cli-reference.md'
path = ROOTS['connector'] / 'docs/cli-reference.md'
original[key] = path.read_bytes()
path.write_bytes((HERE / 'connector-cli-reference.current.md').read_bytes())
changes = {}
for key, data in original.items():
    before = HERE / 'before' / key
    before.parent.mkdir(parents=True, exist_ok=True)
    before.write_bytes(data)
    repo, relative = key.split('/', 1)
    current = (ROOTS[repo] / relative).read_bytes()
    changes[key] = {'before_sha256':hashlib.sha256(data).hexdigest(),
                    'after_sha256':hashlib.sha256(current).hexdigest()}
(HERE / 'doc-changes.json').write_text(json.dumps(changes, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'changed_documents':len(changes)}))
