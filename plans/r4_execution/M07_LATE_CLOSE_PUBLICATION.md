# M07 — Receipt publication after the close observation deadline

Core 0.2.34 adds an explicit wait_for_completion option for policy close. It joins the existing retained producer through terminal receipt persistence. Physical drain/interrupt/force deadlines do not change. The default public observation remains bounded; cancellation detaches a waiter, and producer/storage failures propagate.

The Connector daemon and Nexus embedded R4 executor use the complete wait because they own the admitted operation. They therefore preserve the eventual terminal receipt when journal completion crosses the initial observation deadline. No second close is submitted.

Tests hold the terminal write past the deadline, join after the default observer times out, inject a storage failure, cancel a daemon stop observer, and confirm retained publication. The embedded Pi technical integration holds its real Core terminal write beyond the policy duration and still returns SUCCEEDED.

## Evidence and scope

[Installed campaign](test_runs_20260930_late_close.json) and [artifact hashes](evidence/late-close-artifacts.json) record the verified wheels and test outcomes. The shared Core SHA-256 is `67de77b9250fc773887bd4d0f9c2c0cd5ea4af6ee0b433d38d837e58de7018ba`.

This addresses an in-process late-completion path while the publication authority remains usable. Disconnect/reconnect, durable publication obligations, nonempty reconciliation, crash recovery and the remaining M00–M13 acceptance still require implementation and tests. No milestone or release gate is closed.
