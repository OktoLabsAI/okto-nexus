"""Read-only reconciliation of the 40-case currentness cut, not ledger updates."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ledger_path = HERE.parent / 'NEXUS_HOME_ESTADOS_LEDGER_R1.json'
ledger_raw = ledger_path.read_bytes()
ledger = json.loads(ledger_raw.decode('utf-8-sig'))
qualification = HERE / 'operational-currentness/qualification.json'
xml = HERE / 'operational-currentness/junit.xml'
nodes = []
for index, case in enumerate(ET.parse(xml).findall('.//testcase'), 1):
    module, name = case.attrib['classname'], case.attrib['name']
    path = module.replace('.', '/') + '.py'
    source = (ROOT / path).read_text(encoding='utf-8')
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name.split('[')[0])
    layer = ('canonical SQLite + ASGI HTTP; inert in-process Core peer where specified'
             if 'test_operational_sqlite' in module else 'pure normalized metadata/reducer/page contract')
    nodes.append(dict(index=index, node=path + '::' + name, layer=layer, result='PASS',
        seconds=float(case.attrib['time']), source_sha256=hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
        asserts=[dict(line=n.lineno, expression=ast.get_source_segment(source, n.test))
                 for n in ast.walk(function) if isinstance(n, ast.Assert)]))

# Only the node indices above are evidence. Related legacy or other-owner tests
# are deliberately not inherited into this cut.
mapping = {}


def add(short, node_indices, proved, remaining, assessment='PARTIAL', gap='missing_test'):
    mapping['HST-T-' + short] = dict(assessment=assessment,
        proposed_ledger_status='PASS' if assessment == 'PASS' else 'BLOCKED' if assessment == 'BLOCKED' else 'NOT_RUN',
        executed_nodes=node_indices, proved=proved, remaining=remaining, gap_kind=gap)


add('A01', [28, 31], 'Same-agent extra binding contexts exist in a cursor test; SQL preserves registered contexts.', 'No complete v2 two-binding card/target identity assertion for this literal given.')
add('A02', [], 'No claim from these 40 cases.', 'Two canonical projects with the same public ID, All projects labels and project filter.', 'NOT_RUN')
add('A03', [6, 24, 33], 'Mixed blocked/working session facts reduce together; all seven same-binding session refs paginate without repetition; HTTP session page shape is exercised.', 'Mixed-state same-binding SQLite/HTTP dataset and explicit-opening/no-recency assertion are not combined here.')
add('A04', [], 'No shared-work question-owner given in this cut.', 'Shared A/B work with a native question owned only by A, exact actionable refs and no badge on B.', 'NOT_RUN')
add('A05', [], 'No homonymous-operation given in this cut.', 'Same operation ID on two executors, complete result/receipt/revision/target identity.', 'NOT_RUN')
add('A06', [6], 'Without visual filtering, independent productive sibling prevents full block.', 'Apply actual agent/state visual filter while preserving complete hidden-sibling proof.')
add('A07', [], 'No asynchronous controller test in this Python cut.', 'Delayed A response after selecting B; discard data/count/form generation.', 'NOT_RUN')
add('A08', [], 'No valid unlinked human request given in this cut.', 'One independent unknown-origin human occurrence, no synthetic harness and canonical action revalidation.', 'NOT_RUN')
add('B01', [5, 6, 21], 'Current normalized RUNNING yields working, including unrelated external failure; authority mismatch prevents current working.', 'Positive productive receipt/progress through canonical SQLite ingress is not exercised; real opening test is Idle only.')
add('B02', [1, 11, 34], 'Complete terminal normalized operation can yield Idle; real canonical opening/lease with inert peer yields connected/Idle and no extra open.', 'Actual terminal event/receipt plus separate retained delivery in Results, same snapshot.')
add('B03', [1, 3, 31, 32], 'Registered-only normalized context is unknown, not Idle. Actual SQLite fixture has applied lease/READY but no opening receipt; batch emits no runtime-ready proof.', '', 'PASS', 'none')
add('B04', [3, 32], 'Even a stronger control/lease READY fact without opening proof cannot establish Idle.', 'Literal online-host heartbeat-only fixture and public classification, without any session proof, are not explicitly executed.')
add('B05', [14], 'Normalized admitted/PENDING work yields queued rather than working or idle.', 'Actual queued admission/dispatch SQL and its resulting public presentation are not exercised in that test.')
add('B06', [16, 18], 'Unknown/reconciling productive facts do not prove full pause; unknown answer-write outcome remains uncertain.', 'Observation-deadline productive submission scenario with no automatic effects, rather than an answer-write-only example.')
add('B07', [5, 30], 'Incomplete correlation proof prevents Idle; unknown runtime counts are nullable rather than exact zero.', 'Operational/session query failure or resource truncation combined with an apparently empty visible page and SQL instrumentation.')
add('B08', [5], 'Positive normalized working survives unavailable external source.', 'Canonical SQL source failure and exact session read staying enabled; no provider proof is required for this missing test.')
add('B09', [2, 26], 'Expired validity yields unknown and changes semantic revision without an event.', 'Advance the clock over an unchanged originally-idle fact, including actual refresh/SSE client path; test changes validity itself.')
add('B10', [1], 'Closed normalized sessions yield no_active_session.', 'Explicit one_shot policy and actual terminal/closed session plus proof no automatic runtime.start.')
add('B11', [4, 30], 'Unknown/offline is not silently counted as exact zero connected.', 'Confirmed disconnection/revocation given, retained card and disconnected count without a fourth column.', 'PARTIAL')
add('B12', [28], 'Extra same-agent binding contexts remain distinct in a cursor test.', 'A blocked binding A and productive B do not cross-release each other in the operational reducer.')
add('C01', [], 'No explicit is_blocking=false given in the final 40; legacy tests are outside this evidence cut.', 'Current nonblocking question: working harness plus independent request and blocks_session false.', 'NOT_RUN')
add('C02', [6, 25], 'Pure single blocked operation proves full pause; seven requests on one operation are incorporated into one Needs you card with bounded preview.', 'Literal single-question canonical SQLite/HTTP case with no duplicate Active/request card.')
add('C03', [6], 'A blocked and an independently running session produce working/partial with one blocked and one running session.', 'Public board/API independent request and partial-block wording for this exact two-session given.')
add('C04', [], 'No two-session transition-to-terminal given in this cut.', 'Independent sibling ends, same card moves to Needs you and sibling delivery remains separate Results.', 'NOT_RUN')
add('C05', [7], 'An idle sibling does not provide independent progress and cannot release the confirmed user block.', 'Same-binding blocked/idle pair through actual SQLite/HTTP relation.')
add('C06', [14], 'Queue alone is not working or idle.', 'A simultaneous human blocker plus queued operation with unknown dependency; assert unknown global state and independent request.')
add('C07', [], 'No runtime-proven independent/admissible queue fact is represented by these test inputs.', 'Current reducer has no normalized positive independent/admissible queue input/branch. Contract applicability and implementation/proof are needed before this positive case can be qualified.', 'NOT_RUN', 'implementation_or_missing_producer_contract')
add('C08', [], 'No changing nonblocking-to-blocking proof is exercised.', 'Same occurrence ID across proof change and card incorporation/move, without creating a question.', 'NOT_RUN')
add('C09', [25], 'Seven current questions count exactly and all paginate; one harness card incorporates them without independent duplicates.', 'Two distinct productive executions each suspended by its own action (rather than seven questions on the same operation).')
add('C10', [8, 9, 10], 'Unsupported native methods do not acquire Codex blocking semantics; pending operator action remains counted.', 'An actual Nexus coordination handoff/question without native suspension metadata; do not equate that to the native-method fixtures.')
add('C11', [4, 12, 13], 'Stale control/old generation cannot preserve confirmed current placement; exact historical refs can remain known.', 'Expire the original blocker proof while the canonical unanswered occurrence remains open; assert action/context reachability.')
add('C12', [], 'No shared owner-ambiguous occurrence is exercised in these 40.', 'One canonical action linked to multiple connections; independent presentation survives any-owner blocking without duplicate forms.', 'NOT_RUN')
add('D01', [25, 35], 'Question counts/paging and exact canonical decision ID/native-operation correlation are exercised; API accepted one synthetic operator answer.', 'Rendered question/button/exact target browser or CLI focal.')
add('D02', [8, 9, 10], 'Unknown method/adapter blocking is conservatively unknown instead of borrowing requestUserInput.', 'Actual tool-permission request/type plus adapter-specific positive blocking proof where supported, then render/action focal. Current inspected producers do not provide that universal proof.', 'PARTIAL', 'missing_test_and_adapter_specific_contract')
add('D03', [], 'No verification occurrence assigned to operator in these tests.', 'Canonical verifier action/type and proof it does not itself pause the harness, plus presentation.', 'NOT_RUN')
add('D04', [15], 'Agent-directed question creates zero operator actions and no operator-blocking placement.', 'Literal handoff OPEN/unread to another agent, without an operator action.')
add('D05', [25, 33], 'Beyond-preview question pagination and unique IDs/counts are covered, including a real HTTP page envelope.', 'Mixed question and approval types in the same connection, reachable through the rendered control.')
add('D06', [11, 19, 27, 35], 'Registered decision/native write success never becomes resumed; pending actions zero, null blocks and exact confirmation refs; actual 202/native-op row projection.', 'Combined exact blocked-source API scenario plus rendered confirmation/zero-response CTA. No provider is required for the negative application claim.')
add('D07', [11, 12, 13], 'Later arrival time of an old RUNNING never discharges same-execution confirmation; old epoch/owner rejected.', 'Deliver the stale receipt through canonical SQL ingress and observe the client/CLI presentation, beyond normalized metadata.')
add('D08', [11, 12, 13, 19], 'Negative fences deliberately reject write success/arrival/generation as application proof.', 'Positive same-execution application/resume requires an actual producer causal guarantee not present in the reviewed write-receipt contract. Do not manufacture a marker.', 'BLOCKED', 'producer_causal_contract')
add('D09', [11], 'Normalized terminal operation after decision can transition directly to Idle without pretending Working.', 'Canonical terminal/current-ready evidence and separate Results, then client presentation.')
add('D10', [17, 35], 'Refused-before-effect maps to NATIVE_RESPONSE_NOT_APPLIED, zero new human answer, inspection refs retained; canonical accepted decision row is tested separately.', 'Native write refusal receipt through real ingress and rendered inspection/recovery, with no second productive POST.')
add('D11', [], 'No lost-response/recovery transport in this cut.', 'Lose decision HTTP response; recover exact same intent/receipt, prove one decision/write.', 'NOT_RUN')
add('D12', [], 'No two-interface race in this cut.', 'Concurrent stale revision submission and canonical CAS/error/receipt recovery, no duplicate or recipient change.', 'NOT_RUN')
add('D13', [], 'Legacy snooze tests are antecedent, not part of these 40.', 'V2 confirmed block with seen/snoozed occurrence: no release, no new authority.', 'NOT_RUN')
add('D14', [], 'Control expiry/old epoch is not itself approval denial/expiry.', 'Actual denied/expired approval, later native outcome absent, stale revision rejected and no inferred cancellation/Idle.', 'NOT_RUN')
add('H01', [33, 34], 'Actual HTTP root/session/request reads preserve eighteen productive tables; native opens remains one around read in admitted inert case.', 'Result open, inbox/watermark/ACK and adversarial browser interactions; existing auth bookkeeping must remain separately documented.')
add('H02', [24, 28, 29], 'Cursor principal/card/version scope conflicts are fail-closed in pure page tests.', 'Foreign-object HTTP resolver authorization and absence of preview/count leakage; cursor binding is not authority.')
add('H03', [36], 'Synthetic Bearer marker and overlong/whitespace workspace label are redacted/bounded consistently with connection label.', 'Private native params/prompts, hostile HTML/ANSI and browser rendering/security assertions; not a universal telemetry audit.')
add('H04', [15], 'Agent recipient does not become operator action/full user block in normalized reduction.', 'Actual agent-directed occurrence and operator interaction refused canonically through HTTP/browser.')
add('H05', [], 'No badge/bell concurrent submission in this cut.', 'One occurrence through both shortcuts and canonical CAS/idempotent intent under concurrent submission.', 'NOT_RUN')
add('H06', [16, 17, 18, 19, 33], 'Unknown/refused/successful writes remain distinct and read-only GET snapshots preserve productive data.', 'Render/open uncertain result and prove no blind retry action/effect in browser.')
add('H07', [12, 13, 20, 21, 22, 23, 37, 38, 39, 40], 'Old owner/epoch/current-authority/realization mismatch removes current state and confirmation proof.', 'Snapshot then exact detail/decision revalidation after binding/session change; no name-based successor selection.')
add('H08', [33], 'Read-only fixture includes an external working observation and preserves productive tables.', 'Literal external idle/done report, slot/claim/grant invariants and browser projection. Working report is not the same given.')
add('H09', [], 'No reconnect interaction or daemon observation in this cut.', 'Unavailable individual reconnect in card/detail cannot invoke global restart.', 'NOT_RUN')
add('H10', [], 'No actual CLI work plus UI rollback journey in this cut.', 'Root/path/identity/checkpoint and daemon invariants while using/reverting presentation with existing CLI work.', 'NOT_RUN')
add('J01', [6, 25, 30], 'Session block/running and seven human-action units are counted independently of previews; unknown runtime is nullable.', 'Literal two harnesses/three actions/two deliveries/shared work, instrumented SQL and benchmark.')
add('J02', [5, 30], 'Partial proof does not create Idle and unconfirmed runtime does not synthesize exact zero connected/idle.', 'Instrumented actual incomplete operation coverage and counts/actions with complete positive subset.')
add('J03', [], 'Only source batch design is known; it is not a measured query-growth proof.', 'Execute prepared 1/10/100 constant-query/no-provider-fan-out comparison.', 'NOT_RUN')
add('J04', [24, 25], 'Metadata previews and complete page continuation work on seven-item relations.', 'Actual 1000 activities/100000 history dataset, instrumented overview/results, transcript/payload bounds.')
add('J05', [], 'Performance scripts are prepared only.', 'Paired installed-package datasets/hardware, warmups/repeated samples, actual p50/p95/queries/bytes; targets remain unchanged.', 'NOT_RUN')
add('J06', [26], 'Changing receipt observation time alone does not change semantic revision; real validity expiration changes classification/revision.', 'Heartbeat/clock expiry with actual paging and SQL/benchmark, rather than only normalized facts.')
add('K01', [27, 28, 29, 33], 'Backend confirmation placement does not fabricate full block; source API version negotiation/cursor isolation and old metadata absence are covered.', 'Fresh installed frontend validator/assets consuming both contracts and fallback.')
add('K02', [33], 'Read GETs preserve actual receipt/grant/historical fixture table values, including hashes.', 'Previous-version package dataset opened under final installed candidate with historical receipt preservation.')
add('K03', [28, 33], 'V1 source read remains usable and v1/v2 cursor spaces cannot mix.', 'Flag/UI rollback with active productive work, canonical bell/controls and unchanged runtime/IDs/data.')
add('K04', [], 'This cut explicitly uses source-first Nexus.', 'Fresh wheel/sdist/static installed smoke belongs to package owner, not these 40 tests.', 'NOT_RUN')
add('K05', [], 'No end-to-end CLI lifecycle in this cut.', 'Installed connect/work/answer/result without dashboard and unchanged preset/grant on reconnect.', 'NOT_RUN')
add('K06', [], 'This map preserves partial/not-run/blocked and scopes fixture/provider limits; it is not final release acceptance.', 'Root final ledger/install qualification and explicit default gate decision, preserving prior human/AT/native omissions.', 'PARTIAL', 'final_reconciliation')

groups = set('ABCDJHK')
scenarios = []
for spec in ledger['tests']:
    if spec['group'] not in groups:
        continue
    row = mapping[spec['id']]
    scenarios.append(dict(spec=spec, **row,
        evidence=[nodes[index - 1] for index in row['executed_nodes']]))
used = {index for row in scenarios for index in row['executed_nodes']}
report = dict(version=1, scope='Only operational-currentness 40 executed source-first cases',
    ledger_read_sha256=hashlib.sha256(ledger_raw).hexdigest(),
    qualification_sha256=hashlib.sha256(qualification.read_bytes()).hexdigest(),
    junit_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
    counts=dict(test_cases=len(nodes), scenarios=len(scenarios), assessments=dict(Counter(row['assessment'] for row in scenarios))),
    rules=['PARTIAL is an audit assessment only; normative proposed status remains NOT_RUN.',
           'No result from other owners, legacy17, browser, installed package or native campaign is inherited.',
           'PASS B03 is scoped unit + actual SQLite contract, not a provider/process claim.',
           'No new tests, app/runtime actions, source/ledger/Git edits were performed for this map.'],
    nodes=nodes, unmapped_node_indices=sorted(set(range(1, len(nodes) + 1)) - used), scenarios=scenarios)
(HERE / 'operational-scenario-coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
lines = ['# Operational 40-case scenario coverage', '',
    'Read-only proposal. Root owns ledger changes. PARTIAL remains normative NOT_RUN; D08 remains BLOCKED.', '',
    'This cut proves pure normalized facts plus source-first canonical SQLite/ASGI HTTP and inert Core peers. '
    'It does not qualify packaged frontend, real native processes/providers, browser, AT, or benchmark.', '',
    'Counts: ' + json.dumps(report['counts'], ensure_ascii=False), '',
    'The JSON includes every exact executed node, parameter case, source hash, extracted assertion expression, '
    'layer and literal ledger given/when/then. Indices below refer to that 40-node list.', '',
    '| Scenario | Assessment | Executed nodes | Proved / remaining criterion |',
    '| --- | --- | --- | --- |']
for row in scenarios:
    text = row['proved'] + (' **Remaining:** ' + row['remaining'] if row['remaining'] else '')
    lines.append('| ' + row['spec']['id'] + ' | ' + row['assessment'] + ' | ' + ', '.join(map(str, row['executed_nodes'])) + ' | ' + text.replace('|', '/') + ' |')
lines += ['', '## Priority safe gaps', '',
    '- Mixed-session SQLite/API transitions: A03/A06, C01–C06/C08–C09, exact-owner A04/B12 and ambiguous-owner C12.',
    '- Currentness absence positives/negatives: true terminal+live Idle with separate Results; clock-only expiry, '
    'confirmed disconnection and explicit one-shot closure. No real provider is required for these contract fixtures.',
    '- Canonical decision receipt pipeline: D06/D07/D09/D10 beyond normalized metadata; lost response, two tabs, '
    'v2 snooze/seen and denial/expiry need their exact givens. Browser shortcuts still need real browser evidence.',
    '- C07 cannot currently be represented as a positively proven independent/admissible queued operation by the '
    'normalized input/reducer. Resolve source-contract applicability and implementation before making a PASS claim.',
    '- D08 positive causal native application/resumption is blocked by the producer-contract gap; '
    'write success, arrival time and fake markers do not fill it.',
    '- J03–J05 await the controlled package benchmark window. K package/UI/CLI gates belong to later cuts; '
    'none are inherited from source-first cases.', '']
(HERE / 'operational-scenario-coverage.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(report['counts']))
