"""README error table stays in sync with the canonical ``ErrorCode`` catalogue.

Issue #125: the ``## Errors`` table in ``README.md`` is the human-readable
copy of :class:`okto_nexus.errors.ErrorCode`. The catalogue is documented as
frozen, so any drift -- a code added, renamed or removed in ``errors.py``
without the matching README edit, or vice versa -- must fail loudly here
instead of silently shipping a stale table.

Only the table rows are parsed. The paragraph below the table lists
transport-specific codes (``AUTH_FAILED``, ``CROSS_ORIGIN_BLOCKED``, ...).
Those are deliberately *not* members of ``ErrorCode`` and must not be
counted as canonical codes; a separate test below locks in that distinction.
"""

from __future__ import annotations

import re
from pathlib import Path

from okto_nexus.errors import ErrorCode

README_PATH = Path(__file__).resolve().parents[1] / "README.md"

_CODE_RE = re.compile(r"`([A-Z][A-Z0-9_]*)`")
_CATALOG_COUNT_RE = re.compile(r"closed catalog of (\d+) canonical codes")


def _errors_section() -> str:
    text = README_PATH.read_text(encoding="utf-8")
    try:
        section = text.split("## Errors", 1)[1]
    except IndexError:
        raise AssertionError("README.md has no '## Errors' section") from None
    # Stop at the next top-level (##) heading, i.e. "## Development".
    for heading in re.finditer(r"^## ", section, re.M):
        if heading.start() > 0:
            section = section[: heading.start()]
            break
    return section


def _table_codes(section: str) -> list[str]:
    """Codes from the table rows only, in table order, duplicates kept."""
    codes: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if set(stripped) <= set("|-: "):
            continue  # separator row
        if stripped.startswith("| Area"):
            continue  # header row
        codes.extend(_CODE_RE.findall(stripped))
    return codes


def test_readme_error_table_matches_error_code_catalogue() -> None:
    section = _errors_section()
    table_codes = _table_codes(section)
    assert table_codes, "no codes found in the README ## Errors table"

    assert len(table_codes) == len(set(table_codes)), (
        "README ## Errors table lists a code more than once: "
        + ", ".join(sorted({c for c in table_codes if table_codes.count(c) > 1}))
    )

    canonical = {code.value for code in ErrorCode}
    assert set(table_codes) == canonical, (
        "README ## Errors table drifted from ErrorCode: "
        f"missing from README={sorted(canonical - set(table_codes))}, "
        f"extra in README={sorted(set(table_codes) - canonical)}"
    )


def test_readme_error_table_count_matches_catalogue_size() -> None:
    section = _errors_section()
    match = _CATALOG_COUNT_RE.search(section)
    assert match is not None, (
        "README ## Errors section no longer states its canonical-code count"
    )
    assert int(match.group(1)) == len(ErrorCode), (
        f"README says {match.group(1)} canonical codes "
        f"but ErrorCode has {len(ErrorCode)}"
    )


def test_transport_specific_codes_are_not_canonical() -> None:
    """The paragraph under the table names transport codes, not ErrorCode members.

    Guards against the opposite failure mode: someone "fixing" a sync test
    by copying the transport codes into the table (or into ErrorCode).
    """
    section = _errors_section()
    paragraph = section.split("REST adapters also use transport-specific codes", 1)
    assert len(paragraph) == 2, (
        "README ## Errors section no longer documents the transport-specific codes"
    )
    transport_codes = set(_CODE_RE.findall(paragraph[1]))
    assert transport_codes, "no transport-specific codes found in README"
    canonical = {code.value for code in ErrorCode}
    assert transport_codes.isdisjoint(canonical), (
        "transport-specific code(s) leaked into ErrorCode: "
        + ", ".join(sorted(transport_codes & canonical))
    )
