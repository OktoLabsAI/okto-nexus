# Project diagnostics

Inspect the current project without starting a service, opening a harness or
requesting work:

```text
okto-nexus doctor
okto-nexus doctor --profile project-review --json
okto-nexus doctor --profile project-review --check-server --json
```

The default reads existing profile metadata and inspects the selected local
service through its existing ownership/readiness contract. A remote operator
profile makes local service checks NOT_APPLICABLE: the command never starts a
local substitute. Default remote inspection does not open the credential vault
or contact the remote Server.

`--check-server` explicitly permits authenticated GET requests. On a remote
operator client it reads the existing human session from the protected OS vault,
uses its pinned Server origin/identity and verifies current authentication.
It does not log in, renew credentials, follow redirects, refresh inventory, run
executable probes, negotiate MCP, send messages, claim a handoff, issue a grant,
apply setup, resume an uncertain submission or answer a pending question.

The GET observation budget defaults to 10 seconds (`--timeout`, greater than
zero and at most 30), with at most 64 requests and bounded response bodies.
Budget exhaustion is UNKNOWN. Every underlying request remains subject to
canonical authorization. Presence/revision bookkeeping by existing GET handlers
is permitted; no execution or configuration authority is changed. The local
service readiness inspection has its own bound of at most two seconds.

## Proof levels

Every check reports `PASS`, `FAIL`, `UNKNOWN` or `NOT_APPLICABLE`, a code, a reason
and a next action. Findings are independent:

| Check | Evidence |
|---|---|
| Local service | Existing ownership, generation, version and readiness |
| Server reachability | An actual response from the selected Server |
| Operator authentication | Current human/loopback authority; not agent-client authentication |
| Project identity | The selected canonical identity is active |
| Managed connection | Saved scope still resolves to its canonical binding |
| Runtime eligibility | Current canonical open projection; admission rechecks at execution time |
| Provider login | UNKNOWN: no provider process or credential check is performed |
| External client configuration | NOT_APPLICABLE for a managed project profile; otherwise unverified |
| Participant authentication / MCP negotiation | UNKNOWN until separately proven through that client |
| Coordination participation / handoff test | UNKNOWN; a managed connection is not proof of either |
| Managed session | Current control availability of a saved canonical session |
| Work result | Exact productive operation and its canonical result, using saved request correlation |

A new identity review without a committed receipt remains unconfirmed. The
diagnostic does not infer whether an uncertain commit should be repeated. If a
saved submission lacks an operation, it reports that state without submitting it.
If a completed result is found, only its IDs/state are reported: prompts, native
outputs, credentials and arbitrary remote error bodies are omitted. A successful
runtime open alone never counts as productive completion. Reading a result does
not prove MCP participation or a handoff claim/result.

Revoked grants are reported through the Server's current `AUTHORIZATION_REQUIRED`
reason. Review a new grant explicitly with `work authorize` when appropriate;
doctor cannot issue one. A missing build observation remains `NOT_PROBED` and
UNKNOWN; it does not silently probe the executable. Complete any needed provider
login on the execution host before a separately approved connection test.

## JSON and exit codes

JSON has `format_version: 1`, selected `profile`/`topology`, independent `checks`,
status `counts`, explicit effect flags and overall diagnostic `state`:
`failed_checks`, `incomplete` or `checks_passed`. None of these means the project
is universally ready. Inspect the check relevant to the action you intend.

| Exit | Meaning |
|---|---|
| 0 | Report produced with no FAIL checks; UNKNOWN levels may remain |
| 2 | Invalid command-line usage |
| 3 | At least one check returned FAIL |
| 130 | Observation interrupted with Ctrl+C; no work was cancelled |

Use `work status` / `work watch` to inspect the same saved work in detail.
Participant-file validation, active MCP/coordination smoke and real-provider
qualification remain separate work in R3; this command does not pretend those
checks were performed. The Connector retains its own host `doctor` command.
