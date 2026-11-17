# Interpretation after the user's environment clarification

The user clarified that other processes are running on this machine and asked
not to give these performance measurements excessive weight. For this local
delivery, the recorded timings are **diagnostic and non-blocking**. Further
benchmark rounds and optimizations driven solely by these numbers are
deprioritized; functional correctness and usability take priority.

The original500ms read-p95 and2s first-useful-view targets remain reference
targets. The raw R7 observations, threshold misses, paired differences and
failed predecessors remain unchanged. This clarification does not turn a
measured miss into a pass, approve production performance or enable default.
A future controlled performance qualification would need an appropriate
environment and its own evidence.

The earlier "exclusive" windows sequenced **our own** test/build/browser
readers. They did not establish exclusive use of the hardware, control all
unrelated processes or measure their contention. The observed differences
cannot establish that a code change caused a regression. Shared-machine
load may affect both the baseline/candidate timings and the useful-DOM
observation; neither attribution is quantified by these captures.

The three-GET profile still identifies where the sampled process spent time
and proves the result-attention fast path was used. It does not establish a
production bottleneck, justify a Core/Attention rewrite, or require another
optimization round before local usability evaluation. The open correction
plan is retained as a deferred diagnostic option.

This guidance changes the local acceptance policy, not the measurements.
Functional test omissions, adapter/authority contract limitations, human
acceptance and the previous default-rollout gates remain separate.
