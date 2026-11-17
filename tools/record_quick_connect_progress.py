"""Apply explicit evidence annotations, never infer PASS from existing files."""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'NEXUS_QUICK_CONNECT_R1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('id')
    parser.add_argument('status')
    parser.add_argument('--path', required=True)
    parser.add_argument('--scope', required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    path = BASE / args.path
    if not path.resolve().is_relative_to(BASE.resolve()) or not path.is_file():
        parser.error('Select an existing evidence file inside the QC package')
    ledger_path = BASE / 'NEXUS_QUICK_CONNECT_LEDGER_R1.json'
    value = json.loads(ledger_path.read_text('utf-8'))
    rows = [row for group in ('tasks', 'tests', 'requirements') for row in value[group] if row['id'] == args.id]
    if len(rows) != 1:
        parser.error('Select one existing ledger ID')
    row = rows[0]
    row['status'] = args.status
    evidence = dict(path=args.path, scope=args.scope, commit=args.commit)
    if evidence not in row.setdefault('evidence', []):
        row['evidence'].append(evidence)
    ledger_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(id=args.id, status=args.status, evidence=evidence)))


if __name__ == '__main__':
    main()
