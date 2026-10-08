"""CI partitioning must preserve the complete regression inventory."""
import importlib.util
from pathlib import Path


def load_runner():
    path = Path(__file__).resolve().parents[1] / 'tools' / 'ci_installed.py'
    spec = importlib.util.spec_from_file_location('installed_ci_partition_check', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partitions_cover_every_test_file_once():
    runner = load_runner()
    expected = {p.relative_to(runner.ROOT).as_posix()
                for p in (runner.ROOT / 'tests').rglob('*.py')
                if p.name.startswith('test_') or p.name.endswith('_test.py')}
    parts = runner.partition_tests(['tests'], 4)
    flattened = [path for part in parts for path in part]
    assert all(parts)
    assert set(flattened) == expected
    assert len(flattened) == len(expected)
    assert parts == runner.partition_tests(['tests', 'tests/execution_r4'], 4)


def test_partitioning_preserves_explicit_files_and_rejects_missing_paths(tmp_path):
    import pytest
    runner = load_runner()
    (tmp_path / 'manual.py').write_text('def test_case(): pass', encoding='utf-8')
    assert runner.partition_tests(['manual.py'], 1, root=tmp_path) == [['manual.py']]
    with pytest.raises(ValueError, match='does not exist'):
        runner.partition_tests(['missing'], 4, root=tmp_path)
    with pytest.raises(ValueError, match='positive'):
        runner.partition_tests(['manual.py'], 0, root=tmp_path)
