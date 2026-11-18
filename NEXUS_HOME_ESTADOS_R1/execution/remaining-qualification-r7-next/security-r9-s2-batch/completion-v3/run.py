"""Reviewed completion-locator counterpart layered on the immutable reader variant."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    spec = importlib.util.spec_from_file_location('s2_reader_v2_layer', BASE / 'reader-v2/run.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    original_validate = reader.validate

    def validate(gate_path):
        proof = original_validate(gate_path)
        gate = json.loads(gate_path.read_text())
        manifest = json.loads((HERE / 'manifest.json').read_text())
        assert gate['completion_variant_manifest_sha256'] == sha(HERE / 'manifest.json')
        assert gate['completion_template_sha256'] == sha(HERE / 's2-reported.js')
        for name, expected in manifest['variant_pins'].items():
            assert sha(HERE / name) == expected, name
        assert sha(BASE / 's2-reported.js') == manifest['base_template_sha256']
        assert sha(BASE / 'reader-v2/manifest.json') == manifest['reader_manifest_sha256']
        return {**proof, 'completion_variant_manifest_sha256': sha(HERE / 'manifest.json'),
                'completion_template_sha256': sha(HERE / 's2-reported.js')}

    original_read = Path.read_text

    def template(path, *args, **kwargs):
        if Path(path).resolve() == (BASE / 's2-reported.js').resolve():
            return original_read(HERE / 's2-reported.js', *args, **kwargs)
        return original_read(path, *args, **kwargs)

    reader.validate = validate
    try:
        # Only host template loading is substituted; installed app is separate.
        with patch.object(Path, 'read_text', template):
            return reader.main()
    finally:
        reader.validate = original_validate


if __name__ == '__main__':
    raise SystemExit(main())
