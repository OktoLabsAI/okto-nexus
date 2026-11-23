"""Validate the execution ledger against the preserved SI-R1 specification."""

import json
import sys
from collections import Counter
from pathlib import Path

LEDGER = 'NEXUS_SESSOES_INTERATIVAS_LEDGER_R1.json'
BASE = Path(__file__).resolve().parents[1] / 'NEXUS_SESSOES_INTERATIVAS_R1'
STATES = {
    'tasks': {'TODO', 'IN_PROGRESS', 'IMPLEMENTED', 'VERIFIED', 'BLOCKED'},
    'tests': {'NOT_RUN', 'PASS', 'FAIL', 'BLOCKED'},
    'phases': {'NOT_STARTED', 'IN_PROGRESS', 'VERIFIED', 'BLOCKED'},
}


def check(base: Path) -> dict:
    base = base.resolve(strict=True)
    baseline = json.loads((base / 'input' / LEDGER).read_text(encoding='utf-8'))
    current = json.loads((base / LEDGER).read_text(encoding='utf-8'))
    specification = {key: value for key, value in current.items() if key != 'execution'}
    specification['status'] = baseline['status']

    files: set[Path] = set()
    references = 0
    for group, allowed in STATES.items():
        specification[group] = []
        baseline_rows = baseline[group]
        rows = current[group]
        if [row['id'] for row in rows] != [row['id'] for row in baseline_rows]:
            raise ValueError(f'{group}: row identities or order changed')
        for row, original in zip(rows, baseline_rows, strict=True):
            ident, state = row['id'], row['status']
            if state not in allowed:
                raise ValueError(f'{ident}: invalid state {state}')
            paths: set[Path] = set()
            if 'evidence' in original:
                for evidence in row['evidence']:
                    name = evidence['artifact_path'] if isinstance(evidence, dict) else evidence
                    relative = Path(name)
                    if relative.anchor or '..' in relative.parts:
                        raise ValueError(f'{ident}: evidence path must remain inside the plan directory')
                    path = (base / relative).resolve()
                    if not path.is_relative_to(base) or not path.is_file():
                        raise ValueError(f'{ident}: unavailable evidence {name}')
                    if path in paths:
                        raise ValueError(f'{ident}: duplicate evidence {name}')
                    paths.add(path)
                if state in {'PASS', 'IMPLEMENTED', 'VERIFIED'} and not paths:
                    raise ValueError(f'{ident}: {state} requires evidence')
            references += len(paths)
            files.update(paths)
            normal = row | {'status': original['status']}
            if 'evidence' in original:
                normal['evidence'] = original['evidence']
            specification[group].append(normal)

    if specification != baseline:
        raise ValueError('The execution ledger changed the plan specification')

    return {
        'status': 'PASS',
        'scope': 'specification_and_evidence_references',
        'counts': baseline['counts'],
        'states': {group: dict(sorted(Counter(row['status'] for row in current[group]).items()))
                   for group in STATES},
        'evidence_references': references,
        'distinct_evidence_files': len(files),
        'outstanding_scenarios': [row['id'] for row in current['tests'] if row['status'] != 'PASS'],
    }


def main() -> int:
    try:
        result = check(BASE)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
