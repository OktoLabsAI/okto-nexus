"""Release evidence detects changed dashboard/build inputs without hashing caches."""
import importlib.util
from pathlib import Path


def test_campaign_tracks_ui_build_and_runner_changes(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'tools/ci_installed.py'
    spec = importlib.util.spec_from_file_location('campaign_inputs_under_test', script)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, 'ROOT', tmp_path)
    included = ('frontend/src/components/Choice.tsx', 'frontend/src/style.css',
        'frontend/public/logos/mark.svg', 'frontend/package-lock.json', 'frontend/vite.config.ts',
        'frontend/index.html', 'tools/ci_installed.py', 'tools/build_validation_artifacts.py',
        '.github/workflows/ci.yml')
    excluded = ('frontend/node_modules/react/index.js', 'frontend/dist/assets/index.js',
                'frontend/tsconfig.tsbuildinfo', 'plans/r4_execution/evidence/result.json')
    for name in (*included, *excluded):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'before')
    initial = runner.input_hashes()
    assert set(initial) == set(included)
    for name in included:
        (tmp_path / name).write_bytes(b'changed')
        after = runner.input_hashes()
        assert {path for path in initial if initial[path] != after[path]} == {name}
        (tmp_path / name).write_bytes(b'before')
    for name in excluded:
        (tmp_path / name).write_bytes(b'generated output')
    assert runner.input_hashes() == initial
    (tmp_path / included[0]).unlink()
    assert set(initial) - set(runner.input_hashes()) == {included[0]}
