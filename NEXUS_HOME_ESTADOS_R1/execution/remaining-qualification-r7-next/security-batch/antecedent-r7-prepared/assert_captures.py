"""Offline assertions over captured snapshots, never a substitute for a run.

The future runner must request the named controls and preserve failures/raw
captures. This script does not launch that runner or qualify absent clauses.
"""
import argparse
import json
from pathlib import Path


def compare(root, before, after):
    left = json.loads((root / ('security-' + before + '.json')).read_text())['tables']
    right = json.loads((root / ('security-' + after + '.json')).read_text())['tables']
    assert left == right, 'Canonical table drift; retain the raw cut, no ignore list'
    return sorted(left)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--control-root', type=Path, required=True)
    parser.add_argument('--case', choices=['S1-passive', 'S2-publication'], required=True)
    args = parser.parse_args()
    root = args.control_root.resolve()
    assert root.name == 'control' and root.parent.name.startswith('nexus-hst-browser-')
    if args.case == 'S1-passive':
        tables = compare(root, 'before-get', 'after-get')
    else:
        tables = compare(root, 'before-obs', 'after-idle')
        compare(root, 'before-obs', 'after-completion')
        owner = json.loads((root / 'security-observation-owner.json').read_text())
        assert owner['token_written'] is False and owner['generation'] >= 1
    print(json.dumps({'status':'PASS_CAPTURED_TABLE_ASSERTIONS_ONLY', 'case':args.case,
                      'tables':tables, 'browser_qualified':False, 'ledger_promoted':False}))


if __name__ == '__main__':
    main()
