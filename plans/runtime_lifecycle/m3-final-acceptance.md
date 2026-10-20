# M3 final acceptance — isolated availability and recovery

M3 separates connection, authority, capacity and synchronization. The
independent discovery/publication work and per-session recovery are recorded
in the milestone ledger. The [M3p](m3p-preauthorization-session-refusal.md),
[M3q](m3q-startup-refusal-storage-boundary.md),
[M3r](m3r-authorizer-interruption.md) and
[M3s](m3s-positive-native-effect-isolation.md) checks cover refusals before
authorization, interrupted refusal storage, an
authorization failure after Core composition, and an uncertain post-spawn
effect. In the physical Windows case, a healthy sibling served a turn while
the failed session retained `possible_effect=true`; the slot was released only
after `CONTAINER_STOPPED`, and the caller received the uncertainty without
replay.

The [UI-A gate](ui-a-installed-restart-evidence.md) showed Pi, Claude and Codex
Online and answering through the real Meta-harness after an abrupt disposable
Nexus stop, without manual reconnection. [UI-B](ui-b-evidence-audit.md) showed
a new embedded agent serving work while the separate local Connector actively
failed reconciliation, followed by automatic remote recovery. The
[availability audit](m3v-current-availability-audit.md) and M7o's installed
load recorded 18/18 real Pi one-shot results and pool replenishment. The final
[global CI-wheel rollout](m8-global-ci-wheel-rollout.md) retained the same
agents and history, showed all three local runtimes Online, delivered a new Pi
turn with 1/1 ACK, and returned the pool to 4/5 after session retirement.

Core CI 39336889894 and Connector CI 39343006146 each passed 8/8 jobs. Nexus
installed CI 39472894540 passed 24/24 on the final product commit. This closes
the local M3 acceptance: a failed resource did not consume a healthy sibling,
uncertain native effect kept its fence, and current installed agents recovered
and answered without operator action. The original causes of historical L3/L12
reports remain unproven; their absence in current tests is not a causal
diagnosis. A physical Connector host on another machine remains outside the
user-authorized local campaign.
