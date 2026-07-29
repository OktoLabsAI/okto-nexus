### Technical Overview

To fulfill GitHub's standard security conventions and ensure responsible disclosure of vulnerabilities, a `SECURITY.md` file is added to the root of the repository. Nexus handles sensitive data including API keys, local workspace paths, message history, and operator control commands; establishing a secure, private reporting channel prevents zero-day exposures and protects users.

#### Changes Made:
- **`SECURITY.md` added**: Outlines supported versions, private reporting channels (GitHub Private Vulnerability Reporting & email fallback), guidelines for vulnerability reports, response timeline expectations, and safe harbor commitments for security researchers.

---

### File Content: `SECURITY.md`

```markdown
# Security Policy

Nexus takes the security of our software, API keys, local workspace paths, message history, and operator controls seriously. We appreciate the efforts of security researchers and community members who help keep Nexus safe.

## Supported Versions

Security updates and patches are applied to the `main` branch and the latest stable release.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| Latest  | :white_check_mark: |
| < Latest| :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities via public GitHub issues, discussions, or pull requests.**

If you discover a security vulnerability or potential security exposure in Nexus (e.g., API key leaks, unauthorized workspace directory access, message interception, or operator control bypasses), please report it responsibly:

### Disclosure Paths

1. **GitHub Private Vulnerability Reporting**: Go to the **Security** tab of this repository on GitHub and click **Report a vulnerability**.
2. **Email Disclosure**: If private reporting via GitHub is unavailable, send an email to `security@nexus.dev` with the subject line `[Nexus Vulnerability Report]`.

### What to Include in Your Report

To help us evaluate and patch the issue quickly, please include:
- A description of the vulnerability and its potential impact.
- Detailed steps to reproduce or a minimal Proof of Concept (PoC).
- The affected component (e.g., Workspace Handler, API Key Storage, Operator Interface, Message Bus).
- Any suggested remediations or mitigations if available.

## Our Commitments & Expectations

- **Acknowledgement**: We aim to acknowledge receipt of vulnerability reports within 48 hours.
- **Triage & Patching**: We will work to validate the issue and issue a fix or mitigation in a timely manner.
- **Public Disclosure**: We ask that you afford us a reasonable timeframe to address the vulnerability before disclosing it publicly.
- **Safe Harbor**: Good-faith security research conducted in accordance with this policy will be considered authorized, and we will not initiate legal action against researchers acting in good faith.

Thank you for helping keep Nexus and its community secure!
```