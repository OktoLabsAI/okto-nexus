"""Host control-reader counterpart; application, publications and deadlines unchanged."""
import argparse
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BASE_MANIFEST = '25f48720da92f390b4f52a2caf7d21e8d220f2085b4b30787489826e2724e29a'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(gate_path):
    gate = json.loads(gate_path.read_text())
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert gate.get('approved') is True and gate.get('approved_by') == 'root'
    assert gate['case'] == 'S2'
    assert gate['manifest_sha256'] == sha(BASE / 'prepared-manifest.json') == BASE_MANIFEST
    assert gate['reader_variant_manifest_sha256'] == sha(HERE / 'manifest.json')
    assert gate['effective_driver_sha256'] == sha(HERE / 'effective-run.py.txt')
    for name, expected in manifest['variant_pins'].items():
        assert sha(HERE / name) == expected, name
    assert sha(BASE / 'run.py') == manifest['base_driver_sha256']
    assert gate['cut_id'] != 'hst-security-r9-s2-observed-evidence'
    return {'gate_sha256': sha(gate_path), 'variant_manifest_sha256': sha(HERE / 'manifest.json'),
            'effective_driver_sha256': sha(HERE / 'effective-run.py.txt'),
            'base_manifest_sha256': BASE_MANIFEST}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    before = validate(args.gate)  # Before importing driver/delegating allocation.
    driver = types.ModuleType('security_s2_control_reader_counterpart')
    # Base __file__ preserves every helper/template/preflight/output path.
    driver.__file__ = str(BASE / 'run.py')
    exec(compile((HERE / 'effective-run.py.txt').read_text(), driver.__file__, 'exec'), driver.__dict__)
    original_write = driver.write
    allocation = []

    def record(path, value):
        original_write(path, value)
        if path.name == 'security-guard-before.json':
            allocation.append(path.parent)
            original_write(path.parent / 'reader-variant-before.json', before)

    driver.write = record
    result = None
    try:
        result = driver.main()
    finally:
        driver.write = original_write
        if allocation:
            try:
                after = validate(args.gate)
                unchanged = before == after
            except BaseException as error:
                after = {'error_type': type(error).__name__}
                unchanged = False
            original_write(allocation[0] / 'reader-variant-after.json',
                           {'before': before, 'after': after, 'unchanged': unchanged})
            if not unchanged:
                result = 1
    return result if result is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
