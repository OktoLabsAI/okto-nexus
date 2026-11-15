"""Installed-prefix and argv checks only; no product CLI, status or service call."""
from pathlib import Path
import ast
import hashlib
import json
import sys

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
from recovery_context import RecoveryContext

path = R / 'lifecycle-plan.json'
plan_sha = hashlib.sha256(path.read_bytes()).hexdigest()
context = RecoveryContext(path, plan_sha)
for name in context.P['runtime_pins']:
    ast.parse((R / name).read_text(encoding='utf-8'))
assert context.PUBLIC == R / 'public' and context.PRIVATE == R / 'private'
assert not context.PUBLIC.exists() and not context.PRIVATE.exists()
assert all(step['argv'][0] == context.python and '--force' not in step['argv']
           for step in context.C['steps'])
print(json.dumps({'status': 'OFFLINE_INSTALLED_PREFIX_AND_PINS_PASS',
                  'python': sys.executable, 'plan_sha256': plan_sha,
                  'runtime_pins': len(context.P['runtime_pins']), 'effects': 0}))
