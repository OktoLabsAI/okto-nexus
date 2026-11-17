"""Prepare reviewed test copies; apply only after Root's RELEASED_SOURCE gate.

Default mode writes an execution-only preview. No test module is imported or run.
An apply requires a release JSON with author='/root', statement='RELEASED_SOURCE'
and inventory_sha256 equal to the exact reviewed inventory. This is an explicit
workflow acknowledgement, not a cryptographic authorization mechanism.
Existing destinations are always refused, including on a second apply.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import textwrap


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
INVENTORY = BASE / "test-persistence-plan.json"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dumps(node: ast.AST) -> str:
    return ast.dump(node, include_attributes=False)


def assertions(tree: ast.AST) -> list[str]:
    return [dumps(n) for n in ast.walk(tree) if isinstance(n, ast.Assert)]


def edits(text: str, replacements: list[tuple[int, int, str]]) -> str:
    lines = text.splitlines(keepends=True)
    previous = len(lines) + 1
    for start, end, replacement in sorted(replacements, reverse=True):
        if end >= previous:
            raise ValueError("Overlapping portability edits")
        lines[start - 1:end] = [replacement]
        previous = start
    return "".join(lines)


def portable(entry: dict, original: str) -> tuple[str, list[str]]:
    """Closed, source-hash-bound recipes; assertions/fixture inputs stay intact."""
    text = original
    changes = []
    tree = ast.parse(text)
    # Only evidence write_text expressions explicitly using the runner variable.
    replacements = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "write_text"):
            continue
        segment = ast.get_source_segment(text, node)
        if "os.environ['QC_DERIVATIVE_OUTPUT']" not in segment:
            continue
        indent = " " * node.col_offset
        lines = text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno]
        replacement = indent + "if os.environ.get('QC_DERIVATIVE_OUTPUT'):\n"
        replacement += textwrap.indent("".join(lines), "    ")
        replacements.append((node.lineno, node.end_lineno, replacement))
    if replacements:
        text = edits(text, replacements)
        changes.append("optional_evidence_write_text:" + str(len(replacements)))

    if entry["id"] == "QC14":
        old = "QC14 draft, NOT EXECUTED. Copy beside test_quick_connect_cli after review."
        if text.count(old) != 1:
            raise ValueError("QC14 docstring changed")
        text = text.replace(old, "QC14 canonical regression scenarios; historical external cuts are recorded in execution.")
        changes.append("remove_obsolete_preexecution_docstring")

    if entry["id"] == "QC25locks":
        old = "assert all(pathlib.Path(value).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()) for value in origins.values())\n"
        # This line exists ONLY inside the PROBE string, not the test AST.
        probe = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "PROBE" for t in n.targets))
        if not isinstance(probe.value, ast.Constant) or probe.value.value.count(old) != 1:
            raise ValueError("QC25 expected installed-origin probe line absent")
        text = text.replace(old, "# Installed-origin enforcement belongs to the qualification runner.\n", 1)
        changes.append("remove_only_PROBE_installed_prefix_assertion")
        old = "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP"
        if text.count(old) != 1:
            raise ValueError("QC25 creationflags changed")
        text = text.replace(old, "creationflags=getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)")
        changes.append("platform_safe_process_group_flag")

    if entry["id"] == "QC27":
        name = "def test_h09_windows_json_resume_vector_roundtrip_without_a_shell("
        if text.count(name) != 1:
            raise ValueError("QC27 H09 function changed")
        text = text.replace(name, "@pytest.mark.skipif(os.name != 'nt', reason='Windows argv scenario')\n" + name)
        changes.append("skip_specific_Windows_argv_case_on_other_platforms")

    if entry["id"] == "QC28POSIX":
        text = text.replace("import os\n", "import os\nimport pytest\n", 1)
        anchor = "def test_c15_real_case_sensitive_repo_and_repo_are_distinct(tmp_path):\n"
        if text.count(anchor) != 1:
            raise ValueError("QC28 case-sensitive function changed")
        # Capability fixture only skips an unavailable given, never changes asserts.
        insertion = """pytestmark = pytest.mark.skipif(os.name != 'posix', reason='POSIX filesystem semantics')


@pytest.fixture
def case_sensitive_fs(tmp_path):
    upper, lower = tmp_path / 'qc-capability-A', tmp_path / 'qc-capability-a'
    upper.mkdir()
    try:
        try:
            lower.mkdir()
        except FileExistsError:
            pytest.skip('Filesystem is not case-sensitive')
        lower.rmdir()
    finally:
        upper.rmdir()


@pytest.fixture
def directory_symlinks(tmp_path):
    target, link = tmp_path / 'qc-capability-target', tmp_path / 'qc-capability-link'
    target.mkdir()
    try:
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip('Directory symlinks are unavailable')
        link.unlink()
    finally:
        target.rmdir()


"""
        text = text.replace(anchor, insertion + "@pytest.mark.usefixtures('case_sensitive_fs')\n" + anchor)
        anchor = "def test_posix_symlink_resolves_same_physical_identity_and_profile(tmp_path):\n"
        if text.count(anchor) != 1:
            raise ValueError("QC28 symlink function changed")
        text = text.replace(anchor, "@pytest.mark.usefixtures('directory_symlinks')\n" + anchor)
        changes.append("POSIX_module_skip_and_test_only_filesystem_capability_fixtures")

    if entry["id"] == "QC34ancestorPrivacy":
        old = "audit = Path(os.environ['QC_DERIVATIVE_OUTPUT']) / 'file-read-audit.jsonl'"
        if text.count(old) != 1:
            raise ValueError("QC34 exact audit sink assignment changed")
        text = text.replace(old, "audit = Path(os.environ.get('QC_DERIVATIVE_OUTPUT', str(tmp_path))) / 'file-read-audit.jsonl'")
        changes.append("audit_sink_fallback_to_owned_tmp_path_when_runner_env_absent")

    after = ast.parse(text)
    # Assert contents (including all strict QC34 one-byte proofs) are immutable.
    if sorted(assertions(tree)) != sorted(assertions(after)):
        raise ValueError("A historical assertion was modified")
    before_functions = {n.name: dumps(n.args) for n in ast.walk(tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    after_functions = {n.name: dumps(n.args) for n in ast.walk(after)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if any(after_functions.get(name) != args for name, args in before_functions.items()):
        raise ValueError("A historical function signature was modified")
    compile(text, entry["target"], "exec")
    return text, changes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--release-file", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="New evidence directory under this execution directory")
    args = parser.parse_args()
    raw_inventory = INVENTORY.read_bytes()
    inventory = json.loads(raw_inventory)
    inventory_sha = sha(raw_inventory)
    if args.apply:
        if args.release_file is None:
            parser.error("--apply requires Root's --release-file after RELEASED_SOURCE")
        release = json.loads(args.release_file.read_text(encoding="utf-8"))
        if (release.get("author") != "/root" or release.get("statement") != "RELEASED_SOURCE"
                or release.get("inventory_sha256") != inventory_sha):
            parser.error("Release acknowledgement is absent or does not match this inventory")
    out = args.output.resolve()
    if not out.is_relative_to(BASE) or out == BASE or out.exists():
        parser.error("--output must be a NEW directory strictly below execution")
    prepared = []
    targets = set()
    for entry in inventory["entries"]:
        source = Path(entry["source_path"])
        raw = source.read_bytes()
        if sha(raw) != entry["sha256"]:
            raise ValueError("Original source hash mismatch: " + entry["id"])
        target = (ROOT / entry["target"]).resolve()
        if (target.parent != ROOT / "tests" / "quick_connect" or target in targets
                or target.exists() or target.is_symlink()):
            raise ValueError("Invalid, duplicate or existing destination: " + str(target))
        targets.add(target)
        normalized = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        if sha(normalized.encode("utf-8")) != entry["normalized_utf8_lf_sha256"]:
            raise ValueError("Normalized source hash mismatch: " + entry["id"])
        final, changes = portable(entry, normalized)
        prepared.append((entry, source, target, raw, normalized, final, changes))
    # Validate EVERY source/destination/recipe before any copy or report creation.
    out.mkdir(parents=True)
    records = []
    for entry, source, target, raw, normalized, final, changes in prepared:
        stem = entry["id"].replace("+", "-")
        before_ast = dumps(ast.parse(normalized))
        after_ast = dumps(ast.parse(final))
        diff = "".join(difflib.unified_diff(normalized.splitlines(True), final.splitlines(True),
                                         fromfile=str(source), tofile=entry["target"]))
        (out / (stem + ".patch")).write_text(diff, encoding="utf-8", newline="\n")
        (out / (stem + ".ast.json")).write_text(json.dumps({"before": before_ast, "after": after_ast,
            "historical_assertions_unchanged": True, "historical_function_signatures_unchanged": True},
            indent=2) + "\n", encoding="utf-8", newline="\n")
        payload = final.encode("utf-8")
        if args.apply:
            # Exclusive creation is deliberately NOT an overwrite/idempotent skip.
            with target.open("xb") as stream:
                stream.write(payload)
        records.append({"id": entry["id"], "source_path": str(source), "original_sha256": sha(raw),
            "target": entry["target"], "normalized_sha256": sha(normalized.encode("utf-8")),
            "persisted_sha256": sha(payload), "changes": changes, "copied": args.apply,
            "diff": stem + ".patch", "ast": stem + ".ast.json"})
    report = {"mode": "APPLIED" if args.apply else "PREVIEW_ONLY_NO_TEST_COPIES",
        "inventory_sha256": inventory_sha, "records": records, "tests_executed": False,
        "historical_evidence_unchanged": True,
        "qualification_required": "Run all persisted files on final rebuilt package; no historical PASS inherited"}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"mode": report["mode"], "files": len(records), "report": str(out / "report.json")}))


if __name__ == "__main__":
    main()
