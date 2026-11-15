# Extra Home browser qualification

Eight scoped browser checks passed: back/forward, fresh exact deep-link,
malformed reference refusal, foreign-workspace refusal, missing canonical
record refusal, empty setup CTA, first-burst live-region batching, and actual
light/dark menu with360px keyboard request open/close and focus restoration.

**H02 finding:** a second distinct burst updates visible work but produces no
new aria-live DOM mutation. OperationalHome sets the identical announcement
string repeatedly, so React suppresses the second text update. This is a DOM
finding; no claim about a human screen-reader experience was made. Reported to
Root and the UI owner before any product edits.

**F02 observation:** request CTA is prominent. The idle single-agent fixture
still has five regions, four empty/disabled, plus the recent-activity section.
The screenshot is supplied for literal UX review; this audit introduces no
arbitrary number of permitted panels.

Initial deep-link/theme timeouts were harness errors (background inertness and
closed menu), corrected only in the test harness. Both original and delta
results remain. No product files, services, provider, real data or user tabs
were changed. The separate CLI session used cached tooling without installation.
