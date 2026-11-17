"""Report only sensitive field paths, never their values; own evidence only."""
from pathlib import Path
import json
import re
import sys

pattern = re.compile(r'^(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|cookie|set-cookie|password|secret|agent_key)$', re.I)
found = []

def walk(value, path):
    if isinstance(value, dict):
        for key, child in value.items():
            if pattern.match(key) and isinstance(child, str) and child:
                found.append(path + '/' + key)
            walk(child, path + '/' + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, path + '/' + str(index))

root = Path(sys.argv[1])
for path in root.rglob('*.json'):
    walk(json.loads(path.read_text(encoding='utf-8')), str(path))
print(json.dumps({'nonempty_sensitive_named_string_paths': found}))
raise SystemExit(1 if found else 0)
