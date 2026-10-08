"""Retired interfaces must keep explicit, executable replacement references."""
import ast
import json
from pathlib import Path


def test_retired_runtime_contracts_have_current_regression_references():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(Path(__file__).with_name('runtime_contract_retirements.json').read_text())
    assert len(manifest['source_revision']) == 40
    retired = {item['test'] for item in manifest['retirements']}
    assert len(retired) == len(manifest['retirements'])
    for item in manifest['retirements']:
        assert item['reason'] and len(item['source_sha256']) == 64
        assert item['replacements'], item['test']
        for reference in item['replacements']:
            assert reference not in retired
            path, function = reference.split('::')
            tree = ast.parse((root / path).read_text(encoding='utf-8'))
            node = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function), None)
            assert node is not None and node.name.startswith('test_'), reference
            assert not any('pytest.mark.skip' in ast.unparse(d) or 'pytest.mark.xfail' in ast.unparse(d)
                           for d in node.decorator_list), reference
