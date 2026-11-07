from pathlib import Path
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
target=repo/'plans/agent_ops/evidence/r3-cooperative-drain'
target.mkdir(exist_ok=False)
def copy(source,relative):
    dest=target/relative
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,dest)
source=root.parent/'svc07-nexus-drain-o8tm0ay4'
report=json.loads((source/'nexus-source-qualification.json').read_text())
for name in ['qualification.py','nexus-source-qualification.json',*report['reports']]:
    copy(source/name,'source/'+name)
for name,digest in report['source_files'].items():
    assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest,name
for directory in ('nexus-installed-v1','nexus-installed-fixture-retry'):
    for p in (root/directory).rglob('*'):
        if p.is_file() and p.suffix in {'.json','.xml','.txt'}:
            copy(p,'installed/'+directory+'/'+p.relative_to(root/directory).as_posix())
for name in ('manifest.json','source-comparison.json','build.log'):
    copy(root/'nexus-wheel-v1'/name,'build/'+name)
for name in ('qualify_nexus.py','retry_nexus.py','nexus-snapshot-v1.json','third-party.txt','curate_nexus.py'):
    copy(root/name,'preparation/'+name)
def cases(directory):
    path=root/directory/'canonical/tests.xml'
    return {c.attrib['classname']+'::'+c.attrib['name']:c for c in ET.parse(path).iter('testcase')}
first=cases('nexus-installed-v1')
retry=cases('nexus-installed-fixture-retry')
assert len(first)==247 and len(retry)==62
assert all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in retry.values())
final={**first,**retry}
assert len(final)==292
assert all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in final.values())
for directory in ('nexus-installed-v1','nexus-installed-fixture-retry'):
    assert json.loads((root/directory/'canonical/campaign.json').read_text())['changed_inputs']==[]
summary={
    'scope':'Windows installed wheels; canonical HTTP/SQLite/Core, synthetic native peers; no real provider, credential or user-task campaign',
    'source_unique_cases':247,'installed_svc07_unique_cases':247,'installed_isolation_cases':45,'installed_total_unique_cases':292,
    'first_installed':{'passed':232,'failed':15,'classification':{'missing_normative_schema':12,'missing_backup_helper':1,'incomplete_existing_fake_owner':2}},
    'retry':{'passed':62,'previously_passing_repeated':2,'new_isolation_cases':45,'failed_cases_resolved':15},
    'product_changed_between_runs':False,'input_changes_during_each_run':[],
    'final_passed_identities':sorted(final),
    'wheels':json.loads((root/'nexus-installed-v1/package-proof.json').read_text()),
    'published_dependencies':{'connector':'ef8e267b8aa58eb5dd8c28387c8cc418551c0f2c','core':'3cdba87857e25b4ad5bdbaed91647bfa55873f91'},
    'limits':['No real M1/M2 acceptance','No registered Windows task/logon/logout/reboot campaign','No cross-platform qualification','Historical failure reports preserved; fixture repair did not change product wheel']}
(target/'qualification.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
(target/'milestone.md').write_text('''# SVC-07: cooperative operator drain

The Core and both hosts now distinguish operator drain from safety containment.
New productive admission closes immediately; already admitted decisions, lease
renewal, result publication and acknowledgements retain their current authority.
Timeout remains pending. Force requires the same reviewed generation and an
expired existing drain. Unknown ownership and active readers retain stores and
the service owner until release. Supervisor stop intent precedes containment.

Nexus source and installed qualification cover 247 unique cases, including 36
new cases. Another 45 installed isolation/recovery cases close the finite
inherited-environment gap from the earlier joint campaign: 292 installed unique
cases overall. Source and installed totals are not additive. The first installed
run retained 232 passes and 15 preparation/fixture failures: 12 missing schema,
one missing backup helper, and two incomplete fake-owner cases. The targeted
retry passed all 62 cases (15 repaired, two overlapping, 45 isolation cases).
Product wheel bytes did not change. Each run retained unchanged input hashes.

The built Nexus package has 691 files, the published Connector 124 and Core 166;
wheel/source/installation checks and pip check passed. The canonical packaging
tool built the frontend, wheel and source distribution. Exact hashes, commands,
raw reports, environment policy and preparation failures are retained here.

This is Windows contract qualification with synthetic native peers. It does not
qualify real provider work, credentials, registered user tasks, login/logout or
reboot. SVC-07 implementation is delivered; those real service/campaign scopes
remain open. The fixed plan and its acceptance targets are unchanged.
''',encoding='utf-8')
print(json.dumps({'path':str(target),'unique_passed':len(final)}))
