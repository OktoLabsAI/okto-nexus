"""Report credential-shaped evidence without printing matched values."""
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent
PATTERNS = {
    'private_key': r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
    'token_like': r'(?i)(?:bearer |sk-|gh[pousr]_|xox[baprs]-)[a-z0-9_-]{20,}',
    'credential_assignment': r'''(?i)["'](?:access_token|refresh_token|api_key|password)["']\s*:\s*["'][^"']{12,}''',
}


def main():
    matches, count, size = [], 0, 0
    for name in sorted(path.name for path in BASE.iterdir() if path.is_dir() and path.name.startswith('qc')):
        for path in (BASE / name).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            count += 1
            size += path.stat().st_size
            if path.suffix not in ('.json', '.jsonl', '.txt', '.log', '.py', '.md', '.xml', '.patch'):
                continue
            content = path.read_text(encoding='utf-8', errors='replace')
            found = {key: len(re.findall(pattern, content)) for key, pattern in PATTERNS.items()
                     if re.search(pattern, content)}
            if found:
                matches.append(dict(path=path.relative_to(BASE).as_posix(), patterns=found))
    print(json.dumps(dict(files=count, bytes=size, matches=matches), indent=2))


if __name__ == '__main__':
    main()
