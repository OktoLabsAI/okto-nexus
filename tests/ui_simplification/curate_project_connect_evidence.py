"""Hash the UI039 public evidence and compare available historical client pins.

No service/provider/authentication calls and no synthetic-state mutations.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/'NEXUS_UI_R1/execution/evidence/pr06-onboarding-browser'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    index=ROOT/'src/okto_nexus/adapters/inbound/http/static/index.html'
    bundle=re.search(r'src="/assets/([^"/]+\.js)"',index.read_text(encoding='utf-8')).group(1)
    names=[
        'frontend/src/projectConnectFlowModel.ts','frontend/src/runtimeApi.ts',
        'frontend/src/components/onboarding/ProjectConnectFlow.tsx',
        'frontend/tests/projectConnectFlow.test.mjs',
        'tests/ui_simplification/browser_project_connect_fixture.py',
        'tests/ui_simplification/browser_project_connect_rejection_checks.js',
        'tests/ui_simplification/test_project_connect_rejection.py',
        'tests/ui_simplification/curate_project_connect_evidence.py',
        'src/okto_nexus/application/connection_setup.py',
        'src/okto_nexus/application/connection_test.py',
        'src/okto_nexus/application/project_preset.py',
        'src/okto_nexus/application/execution_binding_proposals.py',
        'src/okto_nexus/adapters/inbound/http/runtime_v1.py',
        'src/okto_nexus/adapters/inbound/http/static/index.html',
        'src/okto_nexus/adapters/inbound/http/static/assets/'+bundle,
        'src/okto_nexus/adapters/inbound/http/static/assets/index-CXFy-VnM.css',
    ]
    pins={name:sha(ROOT/name) for name in names}
    before=json.loads((DEST/'multi-ready.json').read_text(encoding='utf-8-sig'))
    previous_pins={name.replace('\\','/'):value for name,value in before['source_pins'].items()}
    compared={name:{'before':value,'after':pins[name],'changed':value!=pins[name]}
              for name,value in previous_pins.items() if name in pins}
    latest=json.loads((DEST/'restore-ready.json').read_text(encoding='utf-8-sig'))
    latest_pins={name.replace('\\','/'):value for name,value in latest['source_pins'].items()}
    latest_compared={name:{'before':value,'after':pins[name],'changed':value!=pins[name]}
                     for name,value in latest_pins.items() if name in pins}
    result=dict(final_pins=pins,available_antecedent_comparison=compared,latest_fixture_available_comparison=latest_compared,
        antecedent_client='index-dfy1_5aT.js',final_client=bundle,
        comparison_limit='Only files actually pinned at antecedent start are compared. Backend pins here are final-state pins; they are not retroactively claimed as measured before that start.',
        behavioral_scope='Full synthetic Codex/Claude connection/Finish/Resume is antecedent dfy1; final client proves edited inputs, strict refusal/reload/edit, exact restored project/host labels and unchanged archived configuration without replay. Neither cut launches native/provider sessions.')
    (DEST/'source-pins-final.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    files={str(path.relative_to(DEST)):sha(path) for path in sorted(DEST.iterdir())
           if path.is_file() and path.name!='manifest.json'}
    (DEST/'manifest.json').write_text(json.dumps(dict(files=files),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(pins=len(pins),evidence_files=len(files),compared=len(compared))))


if __name__=='__main__':
    main()
