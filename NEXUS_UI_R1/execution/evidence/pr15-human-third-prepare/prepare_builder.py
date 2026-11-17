"""Copy frozen fixture to a new evidence cut; never modify PR14."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).parent;OLD=ROOT/'NEXUS_UI_R1/execution/evidence/pr14-human-session'
def validate():
    manifest=json.loads((OLD/'manifest.json').read_text())
    bad=[name for name,digest in manifest.items() if hashlib.sha256((OLD/name).read_bytes()).hexdigest()!=digest]
    if bad:raise RuntimeError('Frozen PR14 changed: '+','.join(bad))
    return {'manifest_sha256':hashlib.sha256((OLD/'manifest.json').read_bytes()).hexdigest(),'entries':len(manifest),'mismatches':[]}
before=validate();(HERE/'pr14-manifest-copy.json').write_bytes((OLD/'manifest.json').read_bytes())
source=(OLD/'fixture.py').read_text(encoding='utf-8')
changes=[
 ('import pytest\n','import pytest\nfrom observation_window import ObservationWindow\n'),
 ("for p in [Path(__file__),ROOT/'NEXUS_UI_R1/execution/fixtures.py'", "for p in [Path(__file__),Path(__file__).with_name('observation_window.py'),ROOT/'NEXUS_UI_R1/execution/fixtures.py'"),
 ("requests=[];started=time.monotonic();static=", "requests=[];started=time.monotonic();static="),
 ("actions=[];started=time.monotonic();static=", "actions=[];started=time.monotonic();window=ObservationWindow(started,args.duration);static="),
 ("'observation_window_seconds':args.duration,", "'observation_window_seconds':args.duration,'extend_read_window_file':str(args.ready_file.with_name('extend-read-window.json')),'extension_scope':'Observation only; no grant, ticket or native request expiry change',"),
 ('UI observation can stay30min.', 'UI observation starts60min and can be extended explicitly without changing authority.'),
 ('default=1800','default=3600'),
 ("if not 60<=args.duration<=1800:p.error('finite60..1800seconds required')", "if not 60<=args.duration<=3600:p.error('finite60..3600seconds required')"),
 ("prefix='nexus-ui043-human-'", "prefix='nexus-ui043-third-'"),
 ("if args.stop_file.exists() or time.monotonic()-started>=args.duration:server.should_exit=True;return", "extension=window.consume(args.ready_file.with_name('extend-read-window.json'),time.monotonic())\n            if extension:diagnostics.append({'at':s.clock.now_iso(),'kind':'observation_window_control',**extension})\n            if args.stop_file.exists() or window.expired(time.monotonic()):server.should_exit=True;return"),
 ]
for old,new in changes:
    if old==new:continue
    if source.count(old)!=1:raise RuntimeError('Expected one frozen source anchor: '+old)
    source=source.replace(old,new)
(HERE/'fixture.py').write_text(source,encoding='utf-8')
after=validate();(HERE/'preparation.json').write_text(json.dumps({'status':'PREPARED_NOT_STARTED','old_cut_before':before,'old_cut_after':after,'builder_sha256':hashlib.sha256((HERE/'fixture.py').read_bytes()).hexdigest(),'observation_window_default_seconds':3600,'observation_window_explicit_ceiling_seconds':7200,'authority':'No grant/ticket/TTL change; original lane10min and native request120s remain.','human_trial':'Await root new bundle and explicit human start; participant already exposed/oriented.'},indent=2),encoding='utf-8');print(json.dumps({'before':before,'after':after,'prepared_only':True}))
