Here is the complete solution for adding structured GitHub Issue Forms (`.yml`) under `.github/ISSUE_TEMPLATE/` for **Bug Reports**, **Feature Requests**, and **Integration Requests**.

---

### Technical Overview

GitHub Issue Forms provide structured interactive forms replacing plain markdown templates. They enforce standard fields, required inputs, validation, and auto-labeling, which reduces triage overhead and improves issue quality.

#### Directory Structure
```text
.github/
└── ISSUE_TEMPLATE/
    ├── bug_report.yml
    ├── feature_request.yml
    ├── integration_request.yml
    └── config.yml
```

---

### File Content Specifications

#### 1. `.github/ISSUE_TEMPLATE/bug_report.yml`
```yaml
name: Bug Report
description: Report a bug or unexpected behavior to help us improve.
title: "[Bug]: "
labels: ["bug", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting an issue! Please fill out the form below with as much detail as possible to help us reproduce and fix the bug quickly.

  - type: input
    id: summary
    attributes:
      label: Bug Summary
      description: A clear and concise description of the bug.
      placeholder: "e.g., Application crashes when clicking Export CSV"
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: Steps to Reproduce
      description: Step-by-step instructions on how to reproduce the issue.
      placeholder: |
        1. Go to '...'
        2. Click on '....'
        3. Scroll down to '....'
        4. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: A clear description of what you expected to happen.
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual Behavior
      description: What actually happened, including any error messages.
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant Logs / Stack Trace
      description: Copy and paste any relevant logs, stack traces, or console output.
      render: shell

  - type: textarea
    id: environment
    attributes:
      label: Environment Information
      description: OS version, Python/Node runtime version, library version, browser, etc.
      placeholder: |
        - OS: Ubuntu 22.04 / macOS Sonoma
        - Version: v1.2.0
        - Runtime: Python 3.11 / Node 20
    validations:
      required: false
```

---

#### 2. `.github/ISSUE_TEMPLATE/feature_request.yml`
```yaml
name: Feature Request
description: Propose a new feature, enhancement, or architectural improvement.
title: "[Feature]: "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for taking the time to suggest a new feature!

  - type: textarea
    id: problem
    attributes:
      label: Problem Statement / Motivation
      description: Is your feature request related to a problem or limitation? Describe the user pain point clearly.
      placeholder: "I am frustrated when trying to..."
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution
      description: Describe the feature or solution you would like to see implemented.
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: Describe any alternative solutions or workarounds you have considered.

  - type: textarea
    id: additional_context
    attributes:
      label: Additional Context
      description: Add any context, mockups, screenshots, or design thoughts here.
```

---

#### 3. `.github/ISSUE_TEMPLATE/integration_request.yml`
```yaml
name: Integration Request
description: Request support or integration with a third-party tool, service, SDK, or framework.
title: "[Integration]: "
labels: ["integration"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for proposing an integration!

  - type: input
    id: target_service
    attributes:
      label: Target Tool / Service / SDK
      description: Name and official link of the target service or SDK to integrate with.
      placeholder: "e.g., Datadog / OpenTelemetry / Slack SDK"
    validations:
      required: true

  - type: textarea
    id: use_case
    attributes:
      label: Use Case & Business Value
      description: Describe why this integration is needed and how it benefits developers/users.
    validations:
      required: true

  - type: textarea
    id: proposed_interface
    attributes:
      label: Proposed API / Interface Design
      description: How should this integration interact with the existing codebase or configuration?

  - type: textarea
    id: reference_docs
    attributes:
      label: Documentation & References
      description: Links to target API specs, SDK documentation, or reference implementations.
```

---

#### 4. `.github/ISSUE_TEMPLATE/config.yml` (Optional Form Configuration)
```yaml
blank_issues_enabled: false
contact_links:
  - name: Community Discussions
    url: https://github.com/orgs/community/discussions
    about: Please ask general support or usage questions on GitHub Discussions.
```

---

### Python Setup Automation Script

To apply these templates programmatically into a repository, you can run the following Python script:

```python
#!/usr/bin/env python3
"""
Automation script to generate GitHub Issue Templates for Bugs, Features, and Integrations.
"""

from pathlib import Path

TEMPLATES = {
    ".github/ISSUE_TEMPLATE/bug_report.yml": """name: Bug Report
description: Report a bug or unexpected behavior to help us improve.
title: "[Bug]: "
labels: ["bug", "triage"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for reporting an issue! Please fill out the form below with as much detail as possible to help us reproduce and fix the bug quickly.

  - type: input
    id: summary
    attributes:
      label: Bug Summary
      description: A clear and concise description of the bug.
      placeholder: "e.g., Application crashes when clicking Export CSV"
    validations:
      required: true

  - type: textarea
    id: steps
    attributes:
      label: Steps to Reproduce
      description: Step-by-step instructions on how to reproduce the issue.
      placeholder: |
        1. Go to '...'
        2. Click on '....'
        3. Scroll down to '....'
        4. See error
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected Behavior
      description: A clear description of what you expected to happen.
    validations:
      required: true

  - type: textarea
    id: actual
    attributes:
      label: Actual Behavior
      description: What actually happened, including any error messages.
    validations:
      required: true

  - type: textarea
    id: logs
    attributes:
      label: Relevant Logs / Stack Trace
      description: Copy and paste any relevant logs, stack traces, or console output.
      render: shell

  - type: textarea
    id: environment
    attributes:
      label: Environment Information
      description: OS version, Python/Node runtime version, library version, browser, etc.
      placeholder: |
        - OS: Ubuntu 22.04 / macOS Sonoma
        - Version: v1.2.0
        - Runtime: Python 3.11 / Node 20
    validations:
      required: false
""",
    ".github/ISSUE_TEMPLATE/feature_request.yml": """name: Feature Request
description: Propose a new feature, enhancement, or architectural improvement.
title: "[Feature]: "
labels: ["enhancement"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for taking the time to suggest a new feature!

  - type: textarea
    id: problem
    attributes:
      label: Problem Statement / Motivation
      description: Is your feature request related to a problem or limitation? Describe the user pain point clearly.
      placeholder: "I am frustrated when trying to..."
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution
      description: Describe the feature or solution you would like to see implemented.
    validations:
      required: true

  - type: textarea
    id: alternatives
    attributes:
      label: Alternatives Considered
      description: Describe any alternative solutions or workarounds you have considered.

  - type: textarea
    id: additional_context
    attributes:
      label: Additional Context
      description: Add any context, mockups, screenshots, or design thoughts here.
""",
    ".github/ISSUE_TEMPLATE/integration_request.yml": """name: Integration Request
description: Request support or integration with a third-party tool, service, SDK, or framework.
title: "[Integration]: "
labels: ["integration"]
body:
  - type: markdown
    attributes:
      value: |
        Thank you for proposing an integration!

  - type: input
    id: target_service
    attributes:
      label: Target Tool / Service / SDK
      description: Name and official link of the target service or SDK to integrate with.
      placeholder: "e.g., Datadog / OpenTelemetry / Slack SDK"
    validations:
      required: true

  - type: textarea
    id: use_case
    attributes:
      label: Use Case & Business Value
      description: Describe why this integration is needed and how it benefits developers/users.
    validations:
      required: true

  - type: textarea
    id: proposed_interface
    attributes:
      label: Proposed API / Interface Design
      description: How should this integration interact with the existing codebase or configuration?

  - type: textarea
    id: reference_docs
    attributes:
      label: Documentation & References
      description: Links to target API specs, SDK documentation, or reference implementations.
""",
    ".github/ISSUE_TEMPLATE/config.yml": """blank_issues_enabled: false
contact_links:
  - name: Community Discussions
    url: https://github.com/orgs/community/discussions
    about: Please ask general support or usage questions on GitHub Discussions.
""",
}


def setup_issue_templates():
    """Create .github/ISSUE_TEMPLATE directory and write template files."""
    for relative_path, content in TEMPLATES.items():
        file_path = Path(relative_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        print(f"Created: {file_path}")


if __name__ == "__main__":
    setup_issue_templates()
```