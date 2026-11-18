"""Preserve G02's actual AX and timeout without promoting a missing assertion."""
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
source=(HERE/'curate_g01_variant.py').read_text()
source=source.replace('experience-r8-g01-variant','experience-r8-g02-apply')
exec(compile(source,str(HERE/'curate_g01_variant.py'),'exec'))
root=Path(sys.argv[sys.argv.index('--root')+1]);dest=HERE/'experience-r8-g02-apply'
q=dest/'qualification.json';value=json.loads(q.read_text())
value['status']='PARTIAL_G01_G04_POSITIVE_G02_LOCATOR_ORACLE_INCOMPLETE'
value['interpretation']='G02 real canonical preview1/total2/hasMore and exact relation GET200/total2 passed. Failure AX contains one Harness activity modal and a Choose a session combobox whose placeholder is selected, with distinct CLOSED/READY options and actual project/time labels. getByLabel(exact) timed out despite that AX; getByRole(combobox) is the observed selector. This is an oracle failure, not evidence of a missing product chooser.'
value['not_asserted']=['G02 inputValue assertion was not reached; no-auto-selection only observed in failure AX','G03 exact session choice/output after chooser and meaningful titles','All phases after history']
q.write_text(json.dumps(value,indent=2)+'\n')
for image in root.glob('experience-mobile-*-failure.png'):(dest/image.name).write_bytes(image.read_bytes())
entries={str(p.relative_to(dest)):{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}for p in sorted(dest.rglob('*'))if p.is_file()and p.name!='manifest.json'}
(dest/'manifest.json').write_text(json.dumps(entries,indent=2)+'\n')
print(json.dumps(dict(final_manifest_sha256=hashlib.sha256((dest/'manifest.json').read_bytes()).hexdigest(),qualification=str(q)),indent=2))
