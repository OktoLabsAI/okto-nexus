# M05 — Protected provider credential references

Status: provider vault composed into approved local launch; tools and complete M05 remain open.

The local owner can store or remove a provider credential with the public CLI:

    okto-nexus provider-credentials set --home <nexus-home> --agent-id <agent> --reference vault:openai
    okto-nexus provider-credentials remove --home <nexus-home> --agent-id <agent> --reference vault:openai

Set uses a hidden prompt. Headless callers explicitly use --secret-stdin; no secret argument or read/export command is provided. Successful output contains only the reference, agent and status. Setting an existing reference replaces its value. Agent and resolved Nexus home determine the OS service namespace, so another agent or installation cannot resolve the same reference.

Use the same Nexus home and subject agent as the local realization. For example, prepare that realization with `secret_bindings: {"OPENAI_API_KEY": "vault:openai"}`, then approve its binding through the normal connection flow. The provider value is resolved at launch rather than placed in the realization request.

Windows uses Credential Manager through pywin32. Other platforms require a protected Secret Service or macOS keyring backend; missing, locked or unsupported backends fail without a plaintext fallback. The serve/serve-lite extras declare the corresponding platform dependency. Keyring methods and protected backend names follow the [primary keyring documentation](https://keyring.readthedocs.io/en/latest/index.html).

ApprovedLocalLaunch resolves vault references off the event loop, using the approved agent and home, and passes their material only through Core's prepared child environment. Existing checks revalidate the approved configuration and owner before and after secret resolution. Provider environment references remain supported. Empty, multiline, oversized and Nexus credential values are refused; backend exceptions do not expose material.

## Verification

The corrected source campaign passed nine cases: CLI storage/replacement/removal without secret output; installation/agent isolation; invalid secret rejection; sanitized backend failure; approved public local launch with a vault reference; refusal with no native open when only another agent holds the reference; and actual Windows Credential Manager write/read/delete using a disposable scope. The OS test removes its credential and verifies subsequent lookup fails.

An additional installed CLI probe invokes set/remove in separate isolated Python processes with stdin input and the actual Windows backend. It verifies the stored value through the scoped vault, verifies removal, and confirms no secret in command output or plaintext file in the disposable Nexus home. Its credential is removed in cleanup; the evidence contains no secret material.

The initial source campaign had two failures, retained in provider-vault-source-initial.xml. The pywin32 credential blob requires a Unicode input and returns UTF-16 bytes, which is now handled correctly. The missing-credential test now checks the existing conservative dispatcher fence instead of expecting a synthesized terminal receipt. Final installed results are recorded separately in test_runs_20260930_provider_vault.json; overlapping environments and successive runs are not additive coverage.

Final installed results: 122 passed in the normal environment and 67 overlapping tests passed in the actual no-Connector environment, with pip check. The independent installed CLI/OS-vault probe also passed.

## Remaining fixed-plan work

Session tool capability issuance/storage/renewal and automatic MCP/Pi composition remain to connect. Definitive pre-effect public outcome classification, Linux/macOS OS vault qualification, real provider journeys and full M05/M09 acceptance remain open. The provider vault does not store execution tickets or session tool capabilities.

Core and Connector artifacts are unchanged. Preexisting user UI bytes remain in the Nexus wheel but outside this commit and UI acceptance. The existing Starlette/httpx deprecation warning remains.
