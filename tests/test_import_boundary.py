"""Hexagonal import-boundary guard.

The ``domain`` and ``application`` packages MUST NOT depend on the persistence
or transport infrastructure. This test parses every ``.py`` file under those
packages with the AST module and fails if any imports ``sqlite3`` or ``mcp``
(in any form: ``import x``, ``import x.y``, ``from x import ...``).
"""

from __future__ import annotations

import ast
from pathlib import Path

# Repo root = parent of the tests/ directory.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PKG_ROOT = _REPO_ROOT / "src" / "okto_nexus"

INNER_PACKAGES = ("domain", "application")
FORBIDDEN_ROOTS = ("sqlite3", "mcp")


def _iter_inner_py_files() -> list[Path]:
    files: list[Path] = []
    for pkg in INNER_PACKAGES:
        pkg_dir = _PKG_ROOT / pkg
        files.extend(sorted(pkg_dir.rglob("*.py")))
    return files


def _module_root(dotted: str | None) -> str | None:
    if not dotted:
        return None
    return dotted.split(".", 1)[0]


def _violations_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_root(alias.name) in FORBIDDEN_ROOTS:
                    found.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            # node.level > 0 means a relative import (always allowed here).
            if node.level == 0 and _module_root(node.module) in FORBIDDEN_ROOTS:
                found.append(f"{path}:{node.lineno}: from {node.module} import ...")
    return found


def test_inner_layers_have_files() -> None:
    """Sanity: the scan actually finds source files."""
    files = _iter_inner_py_files()
    assert files, f"No .py files found under {INNER_PACKAGES} in {_PKG_ROOT}"


def test_domain_and_application_do_not_import_infrastructure() -> None:
    """domain/ and application/ must not import sqlite3 or mcp."""
    violations: list[str] = []
    for path in _iter_inner_py_files():
        violations.extend(_violations_in(path))
    assert not violations, "Hexagonal boundary violated:\n" + "\n".join(violations)
