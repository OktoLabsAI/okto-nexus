"""Generate a new10-cut orchestration script, without executing a worker."""
import ast
from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / 'persistent-matrix.py').read_text(encoding='utf-8')
source = source.replace('Prepare or run14 sequential', 'Prepare or run10 sequential')
source = source.replace('--r2-ready', '--candidate-ready').replace('args.r2_ready', 'args.candidate_ready')
source = source.replace('R2 READY required', 'Final READY required')
start = source.index('    for workload, dataset, sizes in ')
end = source.index('    destination.mkdir()', start)
source = source[:start] + '''    # Large paired cuts first; small final-package checks follow.
    for workload, dataset in [('mixed', MIXED), ('open', OPEN)]:
        for variant, ready in [('baseline-v1', BASELINE), ('candidate-v1', args.candidate_ready), ('candidate-v2', args.candidate_ready)]:
            jobs.append(dict(name=f'{workload}-100-{variant}', dataset=dataset, connections=100, variant=variant, ready=ready))
    for size in (1, 10):
        for variant in ('candidate-v1', 'candidate-v2'):
            jobs.append(dict(name=f'mixed-{size}-{variant}', dataset=MIXED, connections=size, variant=variant, ready=args.candidate_ready))
    assert len(jobs) == 10
''' + source[end:]
source = source.replace("R1 = HERE.parent / 'package-hst/READY.json'\n", '')
ast.parse(source)
destination = HERE / 'persistent-final-matrix.py'
assert not destination.exists(), 'Do not overwrite a prepared runner'
destination.write_text(source, encoding='utf-8', newline='\n')
print('Prepared10-cut runner AST PASS; no product imported/worker started')
