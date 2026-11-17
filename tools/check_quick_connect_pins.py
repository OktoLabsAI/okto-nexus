"""Recheck an explicit current-cut source manifest without rewriting evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for name in sys.argv[1:]:
        document = json.loads((ROOT / name).read_text('utf-8'))
        pins = document.get('source_sha256', document.get('source_pins', document))
        assert type(pins) is dict and pins, 'Select a source manifest'
        drift = []
        for name, expected in pins.items():
            path = ROOT / name
            assert path.resolve().is_relative_to(ROOT.resolve()), 'Source pin escapes repository'
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                drift.append(name)
        print(json.dumps(dict(pins=len(pins), drift=drift)))
        assert not drift, drift


if __name__ == '__main__':
    main()
