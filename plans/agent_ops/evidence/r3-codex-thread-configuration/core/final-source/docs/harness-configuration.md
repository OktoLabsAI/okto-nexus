# Harness configuration discovery

`discover_harness_configuration(adapter_id, ...)` is a public, side-effect-free
configuration description. Schema version 1 separates native observations from
parameters the Core currently applies. It does not read credentials, launch a
provider, change permissions, or claim an account can use a model.

The returned document contains adapter/version/candidate identity, a deterministic
revision, parameters (native name, scope, default provenance, observed choices,
and `core_applies`), model-specific effort choices, and human-input capabilities.
Nexus tool approval is separate from harness permission modes and human answers.

Hosts can provide captured Claude CLI help, a Codex `model/list` result, or a Pi
`get_available_models` result. Pi `thinking_levels` describes the currently
selected model only; do not apply it to every model. Unknown values stay unknown.
Raw provider responses and help text are not returned. A missing observation is
not an empty successful catalogue.

`query_harness_configuration(adapter_id, request, ...)` reads through an existing
host-owned authenticated native channel. The callback accepts `(method, params)`
and returns the unwrapped result. Codex pagination is bounded and repeated cursors
are rejected. Pi reads its model catalogue without switching the active model.
The host supplies timeouts and binds the channel to the candidate and account.
Failures propagate. The function never opens a thread, sends a prompt or applies
configuration. Claude uses captured `--help` instead of an invented model RPC.

`LaunchIntent.harness_settings` applies immutable native launch settings. Codex
maps effort to `thread/start.config.model_reasoning_effort`, approval policy to
`approvalPolicy`, and sandbox to `sandbox`. Claude maps effort and permission mode
to CLI flags. Pi maps provider and thinking level to CLI flags. Explicit model
selection is forwarded for all three adapters. The selected settings participate
in the prepared profile fingerprint and the R4 opening receipt binding.

Codex `user_input=enabled|disabled` explicitly controls the experimental
`features.default_mode_request_user_input` thread configuration. This feature
was observed in the installed 0.159.0-alpha.12.1 CLI; it enables native questions
in default mode without selecting plan mode. Omission preserves the harness
setting. The discovery label identifies the experimental status. It is unrelated
to automatic tool approval. The native `isBlocking` boolean is a presentation
hint, not permission to discard a question or manufacture an empty answer.

Codex adapter defaults (`on-request`, `read-only`) are identified as Core defaults,
not inferred account settings. An omitted setting preserves the applicable
default; discovery does not copy defaults into explicit saved configuration.

`validate_harness_configuration(description, values)` validates an explicit
selection against a host-owned observation. Codex effort choices belong to a
particular model. Pi models retain provider identity; an ambiguous model requires
an explicit provider. Codex managed requirements can further restrict approval
policy and sandbox choices. An empty observed enum means no available choices,
never a free-text field. Hosts must validate description provenance and freshness.

The Nexus runtime-options projection starts with a passive description. After a
Codex or Pi session opens, the Core queries its initialized, authorized native
transport and publishes a `core/harness_configuration` lifecycle event. This
observation submits no model prompt. Queries have a total 15-second budget and
individual 5-second deadlines. Discovery failure produces a sanitized system
warning and does not terminate an otherwise usable runtime. Event size is bounded.

Codex also publishes a session-scoped `core/codex_thread_configuration` lifecycle
event from its existing `thread/start` or `thread/resume` response. This records
the reported model, provider, reasoning effort, working directory, approval
policy, reviewer, sandbox and instruction-source paths. It performs no extra
native request and reads no instruction or authentication file. The event names
its response source; it is an observation emitted by Core, not a native
notification or a new grant. It is retained through the normal journal and event
replay paths.

Each field is explicitly `reported`, `missing` or `invalid`. Missing fields are
not filled with configured defaults. Unknown policy members, malformed or
oversized values and values requiring secret redaction cannot establish the
effective policy. Instruction references contain paths only, never their file
contents. This bounded snapshot is separate from the capability catalogue and
does not establish model output, tool execution, account entitlement or a hard
token limit. Its installed protocol tests do not replace a real provider campaign.

The Nexus can use the `core/harness_configuration` catalogue for the same endpoint, installation,
configuration revision and credential epoch for 30 minutes. It reconstructs the
public description instead of trusting arbitrary labels from an event. A changed
configuration or expired observation falls back to the passive description until
another session opens. There is no separate pre-launch authenticated catalogue
refresh yet. Claude publishes a bounded CLI-help observation from the selected
installation using `probe_selected_configuration`. That probe checks the binary
fingerprint before and after execution, filters the environment, owns its process
tree, drains both pipes concurrently and never reads login files. Its timeout is
5 seconds and the retained help text is limited to 128 KiB. `native_parameters`
allows hosts to reconstruct that public observation without retaining raw help.

Human questions are contract input, not tool permission. The intended recipient
is the originating interlocutor; the host must implement and authorize that
routing separately. A Claude permission prompt is an approval request for the
operator. A Claude question is an input request for the interlocutor. For
Claude, `recipient_routing_implemented` is true only when the host enables
native approvals for the session (`native_approvals_enabled`). It is false by
default, and always false for Codex, Pi and managed contracts. Codex, Claude and Pi have input bridges subject to build
qualification. Pi supports native `select`, `confirm`, `input` and `editor`
dialogs and returns the corresponding `extension_ui_response` string, boolean
or cancellation. It does not invent a native multi-select format. The bundled
`nexus_ask_user` tool calls Pi's native UI context to generate these requests.
Requests are bounded and correlated to the active turn generation and native ID;
stale, replayed or mismatched responses do not reach the writer.
Automatic approval must never manufacture an answer to a human question.
