"""Derive only this new supplement driver; no allocation or test execution."""
import ast
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
gate = HERE / "TESTS_READY.json"
assert hashlib.sha256(gate.read_bytes()).hexdigest() == "9399da3f6f3c6bce562b6ef8ba5d6b5b66d864fdeb854abd6af646e78aedbe9c"
target = HERE / "installed_regression.py"
assert not target.exists()
code = (HERE.parent / "installed-supplement-r6/installed_regression.py").read_text()
for old, new in (
    ("PACKAGE=HERE.parent/'package-hst-r6'", "PACKAGE=HERE.parent/'package-hst-r7'"),
    ("assert set(supplement['additions'])=={'tests/home_states/test_results_boundary_completion.py'}",
     "assert set(supplement['additions'])=={'tests/home_states/test_final_boundaries_r7.py'}"),
):
    assert code.count(old) == 1
    code = code.replace(old, new)
anchor = "    supplement=json.loads((HERE/'TESTS_READY.json').read_text())\n"
assert code.count(anchor) == 1
code = code.replace(anchor, anchor + '''    assert hashlib.sha256((HERE/'TESTS_READY.json').read_bytes()).hexdigest()=='9399da3f6f3c6bce562b6ef8ba5d6b5b66d864fdeb854abd6af646e78aedbe9c'
    assert len(expected)==1828 and supplement['expected_nodes']==7
    assert args.shard_count==1 and args.shard_index==0 and args.timeout==300
    source_report=REPO/'NEXUS_HOME_ESTADOS_R1'/supplement['source_qualification']
    assert hashlib.sha256(source_report.read_bytes()).hexdigest()==supplement['source_qualification_sha256']
    assert json.loads(source_report.read_text())['status']=='PASS_SOURCE_SCOPED'
''')
ast.parse(code)
target.write_text(code)
(HERE / "owned_commands.py").write_bytes((HERE.parent / "package-hst-r7/owned_commands.py").read_bytes())
print("New R7 installed supplement driver prepared; no test or allocation")
