from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root=Path(__file__).parent
repo=Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
evidence=repo/'plans/agent_ops/evidence'
assert (evidence/'r3-cooperative-drain/qualification.json').is_file()
source=root.parent/'r3-campaign-refresh-0ssbo8pb/public'
target=evidence/'r3-campaign-proposals'
target.mkdir(exist_ok=False)
shutil.copytree(source,target/'prepared-v2')
shutil.copytree(root.parent/'m1-codex-campaign-proposal-ynzvp8yx/public',target/'prepared-v1')
proposal=json.loads((source/'m1-codex-campaign-proposal-v2.json').read_text())
native=json.loads((source/'native/native-service-campaign-proposal.json').read_text())
proposal['revision']=3
proposal['status']='QUALIFIED_PACKAGES_PREPARED_NOT_AUTHORIZED_NOT_EXECUTED'
proposal['supersedes_proposal_sha256']=hashlib.sha256((source/'m1-codex-campaign-proposal-v2.json').read_bytes()).hexdigest()
proposal['revision_note']='Final candidate wheels accepted after 292 unique installed Nexus cases; complete old proposals retained. Package hashes unchanged. No native task/provider execution authorized or performed.'
for name,path in [('nexus',repo),('connector',repo.parent/'okto-nexus-connector'),('core',repo.parent/'okto-nexus-connector-core')]:
    proposal['source_heads_at_preparation'][name]=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
proposal['source_heads_at_preparation']['qualification']='Commit context before Nexus milestone publication; immutable package hashes and source qualification identify the exact candidate.'
for name,key in [('nexus','okto-nexus'),('connector','okto-nexus-connector'),('core','okto-nexus-connector-core')]:
    package=native['packages'][key]
    proposal['package_pins'][name].update(status='QUALIFIED_WINDOWS_CONTRACTS_ONLY',wheel=package['wheel'],python_path=native['python'],installed_import_path=package['import_path'],installed_payload_verified=True)
    proposal['package_pins'][name].pop('installed_import_sha256',None)
proposal['native_selection']['supporting_proof']='prepared-v1/codex-0.157.0-pure-qualification.json'
proposal['topology']['native_service_proposal_reference']=str(target/'native-service-campaign-proposal.json')
proposal['topology']['native_service_proposal_limit']='Separate exact two-task proposal is prepared, not authorized or executed. Its homes qualify only the empty service cycle; M1 uses the separately listed campaign homes and requires its own reviewed canonical setup. Do not silently register additional tasks under the empty-service authorization.'
native['revision']=4
native['status']='QUALIFIED_PACKAGES_PREPARED_NOT_AUTHORIZED_NOT_RUN'
native['supersedes_proposal_sha256']=hashlib.sha256((source/'native/native-service-campaign-proposal.json').read_bytes()).hexdigest()
native['package_qualification']='r3-cooperative-drain/qualification.json: 292 installed unique cases; wheel hashes unchanged from prepared revision3. No native mutation authorized.'
for name,data in [('m1-codex-campaign-proposal.json',proposal),('native-service-campaign-proposal.json',native)]:
    (target/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(target/'milestone.md').write_text('''# Prepared real campaigns; execution remains pending

The user selected Codex CLI, the already authenticated account and an aggregate
200000-token limit. This selects the proposal only. No real model turn or
credential use has occurred. The downloaded official Codex 0.157.0 executable
matches an exact Core-qualified fingerprint; the personal 0.167.0 installation
was not replaced. The complete binary provenance is retained in prepared-v1.

The current turn contract does not expose a proven rigid aggregate token cap.
The pending choice between a rigid limit and monitored preventive interruption
at 100000 reported tokens remains unanswered. The latter cannot guarantee the
200000 maximum because usage reporting and interruption are asynchronous.
No real campaign starts until that constraint and execution are authorized.

The separate Windows proposal names exactly two absent temporary user tasks,
24 lifecycle actions, port52106, isolated homes and a disposable interpreter.
Its three package hashes match accepted contract-test wheels. Eight import/help
checks and pip check passed; source/wheel/install identity covers691/124/166files.
Only passive exact-task queries ran. Registration/start/stop/enable/remove did
not run. This empty-service proposal does not authorize M1 tasks or credentials.

All earlier preparation failures/proposals/manifests remain unchanged. The
driver's git PATH error after read-only checks is retained; finalization reused
completed checks. No full R3, M1/M2 or native-service acceptance is claimed.
''',encoding='utf-8')
inv=root.parent/'r3-invariants-reconciliation-3t6e33nz'
inv_target=evidence/'r3-invariant-reconciliation'
shutil.copytree(inv,inv_target)
matrix=json.loads((inv_target/'matrix.json').read_text())
acceptance={'scope':matrix['scope'],'accepted_verified':[r['id'] for r in matrix['invariants']],
    'conditional_resolved_by':'plans/agent_ops/evidence/r3-cooperative-drain/qualification.json',
    'conditions':['INV-06/20/21 accepted only after 247 source and installed SVC07 cases and45 isolation cases passed','Architectural/contractual invariants do not mark real campaign acceptance complete'],
    'global_acceptance':False}
(inv_target/'accepted.json').write_text(json.dumps(acceptance,indent=2)+'\n')
# Preserve the agent manifest; this root manifest is generated later after review.
print(json.dumps({'proposals':str(target),'invariants':str(inv_target)}))
