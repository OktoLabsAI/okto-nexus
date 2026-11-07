"""Close the finite AC08 doc/help/schema comparison without rerunning tests."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET

HERE = Path(__file__).parent
NEXUS = Path('D:/Projetos/Techridy/okto_labs_okto_nexus')
CONNECTOR = Path('D:/Projetos/Techridy/okto-nexus-connector')
CORE = Path('D:/Projetos/Techridy/okto-nexus-connector-core')
ROOTS = {'nexus':NEXUS, 'connector':CONNECTOR, 'core':CORE}
SITE = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Lib/site-packages')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(repo, name):
    path = ROOTS[repo] / name
    return {'repository':repo, 'path':name, 'sha256':sha(path)}


def xml_summary(name, wanted=()):
    root = ET.parse(NEXUS / name).getroot()
    cases = list(root.iter('testcase'))
    selected = [c for c in cases if any(text in c.get('name','') for text in wanted)] if wanted else []
    return {'path':name,'sha256':sha(NEXUS/name),
            'scope':'Existing retained qualification; not reexecuted or added to any new test total.',
            'suites':[{k:s.get(k) for k in ('tests','failures','errors','skipped')} for s in root.iter('testsuite')],
            'selected_cases':[{'name':c.get('name'), 'passed':not any(n.tag in {'failure','error','skipped'} for n in c)} for c in selected]}


changes = json.loads((HERE/'doc-changes.json').read_text(encoding='utf-8'))
for key, hashes in changes.items():
    repo, name = key.split('/',1)
    assert sha(ROOTS[repo]/name) == hashes['after_sha256']
helps = json.loads((HERE/'help-checks.json').read_text(encoding='utf-8'))
assert all(r['exit_code'] == 0 for r in helps)
assert not list((HERE/'isolated-profile').rglob('*'))
assert (CONNECTOR/'docs/cli-reference.md').read_bytes() == (HERE/'connector-cli-reference.current.md').read_bytes()
before_headers = re.findall(r'^## (.+)$', (HERE/'before/connector/docs/cli-reference.md').read_text(encoding='utf-8'),re.M)
after_headers = re.findall(r'^## (.+)$', (CONNECTOR/'docs/cli-reference.md').read_text(encoding='utf-8'),re.M)

schemas = []
for path in sorted((CORE/'src/nexus_connector_core/contracts').rglob('*.json')):
    relative = path.relative_to(CORE/'src')
    installed = SITE/relative
    assert installed.is_file() and sha(path) == sha(installed), relative
    schemas.append({'path':relative.as_posix(), 'sha256':sha(path), 'installed_exact_bytes':True})
planning = NEXUS/'plans/contratos/http-target.schema.json'
planning_data = json.loads(planning.read_text(encoding='utf-8'))
assert len(planning_data['$defs']) > 0
legacy_note = (NEXUS/'plans/contratos/README.md').read_text(encoding='utf-8')
assert 'não codecs publicados' in legacy_note

trace_path = NEXUS/'plans/agent_ops/evidence/r3-task-reconciliation/atn-obs/matrix.json'
trace = json.loads(trace_path.read_text(encoding='utf-8'))
selected_proofs = []
for family in ('api','preferences','stream','registration','replay','freshness','external','correlation'):
    for node in trace['proof_bundles'][family]['tests'][:2]:
        proof = trace['test_proofs'][node]
        report = proof['selected_passing_report']
        assert sha(NEXUS/report['path']) == report['sha256']
        tree = ET.parse(NEXUS/report['path']).getroot()
        matched = [c for c in tree.iter('testcase') if c.get('name','').split('[',1)[0] == proof['name']]
        assert matched and all(not any(n.tag in {'failure','error','skipped'} for n in c) for c in matched), node
        selected_proofs.append({'family':family,'test':node,'assertions':proof['assertions'],
                               'source':ref('nexus',proof['source']), 'retained_pass':report})

coverage = [
 {'surface':'Nexus service lifecycle', 'docs':['docs/service-lifecycle.md'],
  'source':['src/okto_nexus/adapters/inbound/cli/service.py','src/okto_nexus/adapters/inbound/http/service_lifecycle.py','src/okto_nexus/bootstrap/server_shutdown.py'],
  'compared':'Generation-fenced explicit force only after pending drain deadline; normal stop/restart, install/enable/disable, upgrade-plan/apply; passive status/logs and no timeout force.',
  'evidence':['plans/agent_ops/evidence/r3-cooperative-drain/qualification.json','plans/agent_ops/evidence/r3-contract-closure/controls/result.json'],
  'result':'Aligned after removing obsolete upgrade-pending aggregate text.'},
 {'surface':'Nexus connect and remote project setup', 'docs':['docs/terminal-connect.md','docs/remote-project-setup.md','docs/terminal-operator.md'],
  'source':['src/okto_nexus/adapters/inbound/cli/connect.py','src/okto_nexus/adapters/inbound/http/remote_setup.py'],
  'compared':'Plan/approve, remote draft/handoff, current review, stable root and child IDs, one-shot material, protected import and completed reconnect; configured is not running work.',
  'evidence':['plans/agent_ops/evidence/pr03-remote-bootstrap/reports.json','plans/agent_ops/evidence/pr03-remote-renewal/reports.json'],
  'result':'Aligned after replacing obsolete statements that participant initialization and remote bootstrap remain unimplemented.'},
 {'surface':'Nexus participant lifecycle', 'docs':['docs/terminal-participant.md'],
  'source':['src/okto_nexus/adapters/inbound/cli/participant.py','src/okto_nexus/adapters/inbound/cli/participant_launch.py','src/okto_nexus/adapters/inbound/cli/participant_remove.py'],
  'compared':'Existing identity, reference-only credential template, explicit plan/apply/remove, CAS recovery, foreground launch distinct from actual client/MCP/work readiness; passive doctor versus explicit active checks.',
  'evidence':['plans/agent_ops/evidence/pr04-participant-init-nexus-installed.xml','plans/agent_ops/evidence/pr04-participant-launch-installed.xml','plans/agent_ops/evidence/pr04-participant-removal-installed-final.xml'],
  'result':'No concrete doc/parser mismatch found; real two-client/provider participation is not inferred from these contracts.'},
 {'surface':'Nexus work', 'docs':['docs/terminal-work.md'],
  'source':['src/okto_nexus/adapters/inbound/cli/work.py','src/okto_nexus/application/terminal_authorization.py'],
  'compared':'Explicit submit/steer/answer/interrupt/close, stable IDs and observation recovery, grant review 1..1440 minutes / 1..1000 actions, no automatic renewal or productive replay.',
  'evidence':['plans/agent_ops/evidence/pr03-terminal-work-final.xml','plans/agent_ops/evidence/pr03-remote-renewal/source/operator/remote-renewal-operator-uncertainty-transport-final.xml'],
  'result':'Aligned after separating delivered onboarding/startup review from pending real-provider/native-login qualification.'},
 {'surface':'Nexus coordination', 'docs':['docs/terminal-coordination.md'],
  'source':['src/okto_nexus/adapters/inbound/cli/coordination.py','src/okto_nexus/application/terminal_coordination.py'],
  'compared':'Message/handoff/request surfaces, original request recovery, 30-day receipt horizon, passive handoff completion and distinct timeout/unknown exit codes.',
  'evidence':['plans/agent_ops/evidence/pr05-coordination-cli-source-terminal-coordination-final-agent.xml','plans/agent_ops/evidence/pr05-coordination-cli-source-coordination-cli-agent-auth-final.xml'],
  'result':'No concrete mismatch found; no creation/observation command was executed during this audit.'},
 {'surface':'Nexus attention API and UI', 'docs':['docs/attention.md'],
  'source':['src/okto_nexus/adapters/inbound/http/attention.py','src/okto_nexus/application/attention.py','frontend/src/attentionController.ts'],
  'compared':'Strict viewing writes, source/preference CAS, page1..200, operator auth, classifiers, five-second budget, SSE/refresh behavior and no canonical business mutation.',
  'evidence':['plans/agent_ops/evidence/r3-task-reconciliation/atn-obs/matrix.json'],
  'result':'Contract aligned; removed obsolete future PR07 client wording. Existing behavior assertions and retained PASS references are included separately.'},
 {'surface':'Nexus external observations and correlation', 'docs':['docs/external-observations.md'],
  'source':['src/okto_nexus/domain/observations.py','src/okto_nexus/domain/observation_correlation.py','src/okto_nexus/adapters/inbound/http/observations.py','src/okto_nexus/config.py'],
  'compared':'Closed version1 report and correlation inputs, current/stale/unavailable projection, TTL3600/future30 defaults, finite quotas, publish-only token, passive reads and private birth proof with no authority/capacity promotion.',
  'evidence':['plans/agent_ops/evidence/r3-task-reconciliation/atn-obs/matrix.json','plans/agent_ops/evidence/pr10-correlation/reports.json'],
  'result':'No concrete mismatch found in reviewed fields/endpoints/defaults. Correlation remains local Windows only as documented.'},
 {'surface':'Connector connect/configure and lifecycle', 'repository':'connector',
  'docs':['docs/connection-configuration.md','docs/service-lifecycle.md','docs/cli.md','docs/cli-reference.md'],
  'source':['src/okto_nexus_connector/cli/main.py','src/okto_nexus_connector/cli/commands/reconnect.py','src/okto_nexus_connector/cli/commands/connect.py'],
  'compared':'All75 parser help blocks, remote draft/current review, protected handoff import, completed rotation reuse, daemon drain/restart and owned-service enablement/upgrades.',
  'evidence':['docs/evidence/cooperative-drain/milestone.md'],
  'result':'Regenerated stale CLI reference; corrected reconnect interruption claim and obsolete upgrade-pending aggregate text.'},
 {'surface':'Core API, participant format and published schemas', 'repository':'core',
  'docs':['docs/api.md','docs/lifecycle.md','docs/participant-config.md','docs/compatibility.md'],
  'source':['src/nexus_connector_core/ports.py','src/nexus_connector_core/drain.py','src/nexus_connector_core/__init__.py'],
  'compared':'Synchronous begin_drain/drain_revision, async status and same-journal-only combination; participant JSON/TOML references, no identity/authority claim; published schema/manifest bytes match installed package.',
  'evidence':['docs/evidence/cooperative-drain/milestone.md'],
  'result':'Completed API method reference; lifecycle contract was current. Core is a library with no new CLI requirement.'},
]
for row in coverage:
    repo = row.get('repository','nexus')
    row['documentation_inventory'] = [ref(repo,name) for name in row['docs']]
    row['source_inventory'] = [ref(repo,name) for name in row['source']]
    row['evidence_inventory'] = [ref(repo,name) for name in row['evidence']]

retained = [xml_summary('plans/agent_ops/evidence/pr03-terminal-work-final.xml'),
            xml_summary('plans/agent_ops/evidence/pr04-participant-init-nexus-installed.xml'),
            xml_summary('plans/agent_ops/evidence/pr04-participant-launch-installed.xml'),
            xml_summary('plans/agent_ops/evidence/pr04-participant-removal-installed-final.xml'),
            xml_summary('plans/agent_ops/evidence/pr05-coordination-cli-source-terminal-coordination-final-agent.xml'),
            xml_summary('plans/agent_ops/evidence/r3-cooperative-drain/installed/nexus-installed-fixture-retry/canonical/tests.xml',('test_capability_public_issue','test_capability_request_rejects'))]
for report in retained:
    assert all(s['failures'] == s['errors'] == s['skipped'] == '0' for s in report['suites']), report['path']

prepared = NEXUS/'plans/agent_ops/evidence/r3-campaign-proposals/prepared-v2/native'
prepared_checks = json.loads((prepared/'read-only-checks.json').read_text(encoding='utf-8'))
prepared_help = []
for path in sorted(prepared.glob('*help*.stdout.txt')):
    assert any(row.get('stdout_sha256') == sha(path) and row['returncode']==0 for row in prepared_checks)
    prepared_help.append(ref('nexus',path.relative_to(NEXUS).as_posix()))

result = {
 'criterion':'AC-08', 'requirement_exact':'Documentação, schemas e ajuda da CLI descrevem o comportamento realmente entregue.',
 'base_commits':{'nexus':'4855abd5','connector':'ef8e267','core':'3cdba87'},
 'plan_sha256':sha(NEXUS/'PLANO_CODEX_NEXUS_INTEGRACAO_ATENCAO_ONBOARDING.md'),
 'recommendation':'AC08 supported for the finite reviewed three-package delivery after committing these documentation corrections; no ledger promotion performed.',
 'scope':'Current lifecycle/connect/participant/work/coordination/OBS/ATN docs, installed parser help and published Core schema resources. Historical reports remain historical evidence, not current user instructions.',
 'actions':{'new_tests':0,'productive_examples_executed':0,'services_started':0,'provider_calls':0,'credentials_used':0,'new_help_commands':10,'parser_imports':1,'rendered_connector_parsers':75,'reused_help_reports':len(prepared_help),'product_edits':0,'schema_edits':0,'ledger_edits':0},
 'changes':changes, 'coverage':coverage, 'new_help_checks':helps, 'reused_help_reports':prepared_help,
 'generated_reference':{'exact_installed_parser_output':True,'before_sections':len(before_headers),'current_sections':len(after_headers),'added_sections':sorted(set(after_headers)-set(before_headers))},
 'schemas':{'published_core_json_resources':schemas,'planning_schema':{'path':'plans/contratos/http-target.schema.json','sha256':sha(planning),'defs':len(planning_data['$defs']),'classification':'Explicit historical planning DTO target, not a published codec or complete current HTTP OpenAPI contract. Existing capability shape assertions are retained; no target schema was relabeled or changed.'},'obs_attention':'Current HTTP/domain closed validators and config bounds were compared directly to the guides; their source references appear in coverage.'},
 'retained_reports_inspected':retained,'retained_assertion_proofs':selected_proofs,
 'initial_report_preserved':xml_summary('plans/agent_ops/evidence/pr03-terminal-work-installed.xml'),
 'clarity_note':'Connector root help says configure is an interactive wizard (JSON optional). The optional JSON input is --file; --json output is explicitly refused in code and documented as unsupported. This short phrase does not assert support for --json. No product/wheel change was made.',
 'limits':['No real provider, native scheduled-task mutation, two physical hosts or actual two-client productive campaign was executed or inferred.','Published historical XMLs were read only and were not reexecuted or aggregated as new test counts.','Planning schemas and old milestone reports were not rewritten as current deployment promises.','No requirement was added for new platforms, a Core CLI, schema generation for every internal API, or rewriting historical evidence.'],
 'validation':{'diff_check_all_three_repositories':'PASS','isolated_profile_files_created':0,'all_help_exit_codes_zero':True,'core_resources_equal_installed':True}
}
assert result['plan_sha256']=='20d0fafdedc793b97a277f5d41355d7d597ff724a77687394215eea3113ba996'
(HERE/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['# AC-08: final documentation, help and schema comparison','',
 'Recommendation: the reviewed final three-package surface supports AC-08 after the eight documentation corrections are committed. No ledger status was changed.','',
 'Only docs changed. Ten isolated Nexus help commands and one Connector parser import completed successfully; all 75 Connector parser blocks generated the exact replacement CLI reference. Six already retained service help reports were reused. No productive example, service, provider or credential was used.','',
 '| Surface | Result |','|---|---|']
lines += ['|'+r['surface']+'|'+r['result']+'|' for r in coverage]
lines += ['', 'The exact changed-file hashes, source/evidence references, preserved assertion-to-PASS mappings and published Core JSON resource comparisons are in `audit.json`. `doc-changes.json` retains before/after hashes; original public docs are under `before/`.','',
 'The existing HTTP planning schema stays classified as planning, not a complete published API contract. The short Connector help phrase “JSON optional” refers to the optional template; `--json` wizard output remains explicitly unsupported.','',
 'Real providers, native Task Scheduler mutation/login/logout, two physical hosts and actual two-client productive campaigns remain outside this audit. Historical test evidence is not claimed as a new run.']
(HERE/'audit.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
allowed = [p for p in sorted(HERE.iterdir()) if p.is_file() and p.name!='manifest.json']
allowed += [p for p in sorted((HERE/'before').rglob('*')) if p.is_file()]
public = HERE/'public'
public.mkdir(exist_ok=True)
files = {}
for path in allowed:
    relative=path.relative_to(HERE)
    target=public/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path,target)
    assert sha(path)==sha(target)
    files[relative.as_posix()]=sha(target)
(public/'manifest.json').write_text(json.dumps({'criterion':'AC-08','files':files,'excluded':['isolated-profile/'],'only_public_artifacts':True},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'changed_docs':len(changes),'coverage_rows':len(coverage),'published_core_json_resources':len(schemas),'artifact_files':len(files),'audit_sha256':sha(HERE/'audit.json'),'manifest_sha256':sha(public/'manifest.json')}))
