"""Offline focal I05 rollup; preserves the original diagnostic qualification."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
run=HERE/'runs/hst-native-zoom-r9-app-1'
original=json.loads((run/'qualification.json').read_text())
supplement=HERE/'offline-pin-supplement/qualification.json'
assert json.loads(supplement.read_text())['matching_original_before']
cases={name:json.loads((run/(name+'-result.private.json')).read_text()) for name in ['app-200','app-100']}
assert all(v['status']=='PASS_I05_EXECUTED_SUBSET' and len(v['checks'])==24 and all(c['pass'] for c in v['checks']) for v in cases.values())
assert not any(original['physical'][key] for key in ['remaining_births','profile_processes','listeners'])
assert original['fixture_cleanup']['exit_code']==0 and not original['fixture_cleanup']['signals']
assert not original['forced_births']
out=HERE/'focal-i05';out.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
images=[p for p in run.glob('i05-app-*.png')]
assert len(images)==6
report=dict(
    status='PASS_FOCAL_I05_BROWSER_WITH_OFFLINE_PIN_SUPPLEMENT',
    original_runtime_status=original['status'],original_runtime_exit=1,
    original_runtime_error=original['cleanup_errors'],
    original_qualification='../runs/hst-native-zoom-r9-app-1/qualification.json',
    original_qualification_sha256=sha(run/'qualification.json'),
    original_manifest_sha256=sha(run/'manifest.json'),
    offline_pin_supplement='../offline-pin-supplement/qualification.json',
    offline_pin_supplement_sha256=sha(supplement),
    assertions={name:dict(passed=len(value['checks']),failed=0,ids=[c['id'] for c in value['checks']],geometry=value['observations']['geometry']) for name,value in cases.items()},
    native_guard_passed=14,app_bootstrap_passed=4,
    canonical_close=original['canonical_close'],physical=original['physical'],fixture_cleanup=original['fixture_cleanup'],
    provider_invocations=original['provider_invocations'],browser_writes=0,page_errors=0,
    image_review=dict(method='Viewed all six exact public PNGs; only synthetic fixture labels, IDs, UI and timestamps visible; no cookie, CAS/approval token or personal input.',images=[dict(path='../runs/hst-native-zoom-r9-app-1/'+p.name,sha256=sha(p)) for p in sorted(images)]),
    limits=['Original runner exit1/final after=null remains immutable; only a later offline check confirms identical pins.', 'A1/A2 canonical runtime.close remain UNKNOWN despite normal physical process exit.', 'Actual Chrome Settings zoom, no CSS/deviceScale/PageScale substitution.', 'Only this inert-protocol dataset: two bindings, three sessions, one operator question; no real provider, AT, human acceptance, all keyboard path or theme expansion.', 'Both cases CSS360: requested720/native200/DPR2 and requested360/native100/DPR1; no 360outer/native200 claim.'],
)
(out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
(out/'README.md').write_text('''# I05 focal native zoom qualification

Two actual app cases passed 24 predicates each, after the 14-predicate native Chrome Settings guard and four bootstrap checks. Native 200% at requested width 720 measured innerWidth 360/DPR 2; native 100% at requested width 360 measured innerWidth 360/DPR 1. Both retained visualViewport.scale 1 and scrollWidth 360.

The three columns stack without overlap, align in x, and long real project labels wrap. With the navigation aside hidden, each category action passed hit-test and opened its exact session/request/result context; closing restored focus to the same originating card/action. The original question remained within its original validity. Browser writes and page errors were zero.

The original runner exited 1: local card variable `a` shadowed the argparse namespace, so the final `check(a.gate)` raised AttributeError. This is an instrumentation failure, preserved in the original qualification. The independent offline supplement imports the frozen check function and passes the gate Path directly: 1,031 payload, 1,829 source and 192 CLI files plus wheel/tool/runtime/input pins match the captured before. It does not allocate or execute another application/browser.

CLI, probe and fixture exited normally (0), without signals/forced containment; all observed own births, own-profile processes and both listeners were absent. B1 close was confirmed; A1/A2 close remain UNKNOWN. Physical absence does not resolve those receipts.

The six public PNGs were viewed and contain synthetic fixture UI only. No AT speech, human acceptance, theme matrix, provider/harness qualification or timing SLO is claimed.
''')
manifest={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in out.iterdir() if p.is_file()}
manifest['../curate_focal.py']=dict(sha256=sha(Path(__file__)),bytes=Path(__file__).stat().st_size)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],manifest_sha256=sha(out/'manifest.json'),images=[p.name for p in images]),indent=2))
