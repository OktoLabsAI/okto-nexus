# Security Policy

## Supported releases

Security fixes are prepared for the latest published Okto Nexus release. When
a fix is released, users should upgrade to the newest available version. Older
versions may not receive backports.

## Reporting a vulnerability

Do not open a public GitHub issue for a suspected vulnerability. Send a private
report to **dev@oktolabs.ai** with:

- the affected version and installation mode;
- the relevant transport, authentication mode, and configuration;
- reproduction steps or a minimal proof of concept;
- the security impact and affected data or permissions;
- any suggested mitigation, if known.

Remove credentials, API keys, session secrets, tokens, private messages,
workspace files, and other sensitive data from the report unless they are
strictly necessary to reproduce the issue. If sensitive material must be
shared, ask for a secure transfer method first.

Okto Labs will evaluate the report and coordinate remediation and disclosure
as appropriate. This policy does not promise a specific response or resolution
time.

## Deployment responsibility

Okto Nexus is designed for local or controlled single-tenant use. Operators are
responsible for access control, TLS termination for remote deployments, host
and filesystem security, secret handling, and timely upgrades. Review the
security and limitations section of the [README](README.md#security-and-limitations)
before deployment.
