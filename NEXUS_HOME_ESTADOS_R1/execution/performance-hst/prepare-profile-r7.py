"""Prepare only: preserve R6 and reuse its exact three-GET diagnostic protocol."""
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
for kind in ('worker', 'launch'):
    source = HERE / f'profile-r6-{kind}.py'
    target = HERE / f'profile-r7-{kind}.py'
    assert not target.exists(), 'Never overwrite a prior diagnostic'
    text = source.read_text(encoding='utf-8').replace('R6', 'R7').replace('r6', 'r7')
    if kind == 'launch':
        text = text.replace('import hashlib\n', 'import argparse\nimport hashlib\n', 1)
        marker = 'HERE=Path(__file__).resolve().parent'
        guard = "parser=argparse.ArgumentParser(allow_abbrev=False)\nparser.add_argument('--window',required=True,choices=['DIAG_WINDOW_OPEN'])\nparser.parse_args()\n\n"
        text = text.replace(marker, guard + marker, 1)
    ast.parse(text)
    target.write_text(text, encoding='utf-8', newline='\n')
print('Prepared R7 worker/launch AST PASS; no application imports/processes/homes allocated.')
