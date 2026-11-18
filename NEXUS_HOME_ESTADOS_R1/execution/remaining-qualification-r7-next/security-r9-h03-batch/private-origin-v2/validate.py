"""Validate input-origin-only variant before any delegation/allocation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
BASE_MANIFEST = 'c7b110ffc3ea488cd090b991df0019dc71f64efded13553a9797a34e021d9293'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(gate_path):
    gate = json.loads(Path(gate_path).read_text())
    manifest = json.loads((HERE / 'manifest.json').read_text())
    assert gate.get('approved') is True and gate.get('approved_by') == 'root'
    assert gate['case'] == 'H03'
    assert gate['manifest_sha256'] == sha(BASE / 'prepared-manifest.json') == BASE_MANIFEST
    assert gate['input_origin_variant_manifest_sha256'] == sha(HERE / 'manifest.json')
    assert gate['input_origin_transform_sha256'] == sha(HERE / 'fixture_transform.py')
    for name, expected in manifest['variant_pins'].items():
        assert sha(HERE / name) == expected, name
    for name, expected in manifest['base_pins'].items():
        assert sha(BASE / name) == expected, name
    return {'gate_sha256': sha(gate_path), 'base_manifest_sha256': BASE_MANIFEST,
            'input_origin_variant_manifest_sha256': sha(HERE / 'manifest.json'),
            'input_origin_transform_sha256': sha(HERE / 'fixture_transform.py')}
