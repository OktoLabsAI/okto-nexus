"""Offline interpretation of captured redacted facts, not a new browser test."""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
CUT=HERE/'experience-r8-session-role'
q=json.loads((CUT/'qualification.json').read_text());terminal=json.loads((CUT/'control/exp-a-terminal.json').read_text())
received=q['results']['panel-after']['checks'][0]['actual']
prior=set(received['ids']['results']);new_deliveries=[i for i in terminal['board']['columns']['results']['items']if i['id']not in prior]
a=next(i for i in terminal['board']['columns']['needs_you']['items']if i['kind']=='harness')
assert a['operational_status']['activity']=='waiting_user'and a['operational_status']['blocking']=='full'
assert len(new_deliveries)==1 and new_deliveries[0]['delivery_semantics']['execution_outcome']=='succeeded'
labels=next(c['actual']for c in q['results']['active']['checks']if c['id']=='G05-authorized-projects-readable')
assert labels and all('Project:'in text and ('Alpha project'in text or'Beta project'in text)for text in labels)
rows={
 'G01':('COMPLETE_CAPTURED','base: entire scope GET200, exact singleton target and marker in one gesture; base operation/grant digest unchanged'),
 'G02':('COMPLETE_CONTROLLED_QUERY_VARIANT','history: real preview=1/total2/hasMore; exact relation GET200, blank choice; two known session options and outputs. No fabricated DTO'),
 'G03':('PARTIAL_TITLE_PRODUCER_GAP','CLOSED/READY/project/Updated and distinct exact outputs captured. Meaningful specific titles remain fallback Session; no invented producer'),
 'G04':('LAZY_REGISTERED_POLICY_SUBSET','Real per_sender effective policy, zero-session context; no runtime operation/grant change. Literal on-demand terminology must be mapped by Root, not a fabricated enum'),
 'G05':('OFFLINE_CAPTURED_LITERAL_CANDIDATE','All captured harness/request/delivery card text contains Project and Alpha/Beta label; equal reviewer IDs in two canonical workspaces. Root decides promotion against existing component evidence'),
 'G06':('PARTIAL_NEGATIVE_ONLY','Null state_since and no invented State since line asserted. Received timestamps observed but no dedicated full received/elapsed-duration oracle'),
 'I01':('PARTIAL_BOUNDED_KEYBOARD','Three populated columns; Tab reaches exact A, Enter opens, keyboard chooses exact A2, Tab/Enter opens native question; modal containment and named menu captured. Full actionable-name inventory/AT not qualified'),
 'I02':('NOT_COMPLETED','moved-close stopped before Escape/close/focus assertions; no focus-return PASS'),
 'I04':('PARTIAL_THEME_STATES','Light/dark preserve labels for states present in that phase. All requested Working/pending/error/unconfirmed combinations were not reasserted in both themes'),
 'I05':('PARTIAL_360_ONLY','Long canonical labels; three stacked columns and no page overflow; captures before question. Native200% zoom and full detail-return clause absent'),
 'F02':('COMPLETE_CAPTURED','Unrelated B close, received authoritative board200, same modal node and exact native-question form retained; real normal Home statuses, zero alerts'),
 'F07':('NOT_COMPLETED','Host proves same A moved to Needs you after sibling terminal, but corresponding browser board read and close/focus were not captured'),
 'F10':('COMPLETE_CAPTURED','Actual external query-port OperationalError -> external unavailable; exact native B2 session/output remains readable; restored source in finally'),
 'F12':('PRIOR_R5_REUSE_PARTIAL','No new decision in this batch. Use prior R5 paused two-poll/canonical202/terminal evidence only; preserve its authority-invariant limitations'),
 'F13':('COMPLETE_CAPTURED','Actual revision changed; Home statuses include Updates are available, normal revalidation and Home updated. No Home/modal role alerts'),
}
review=dict(mode='OFFLINE_REVIEW_NO_RUNTIME',status_changes=False,active_resources=False,source_commit=q['source_commit'],wheel_sha256=q['wheel_sha256'],executed_predicates_passed=sum(v['passed']for v in q['summary'].values()),rows={k:dict(assessment=v[0],evidence=v[1])for k,v in rows.items()},captured_project_text_rows=len(labels),revision_diagnosis=dict(last_captured_received_board=received,host_terminal_revision=terminal['board']['revision'],host_terminal_ids={k:[i['id']for i in v['items']]for k,v in terminal['board']['columns'].items()},host_A_full_block=dict(id=a['id'],connection=a['connection'],status=a['operational_status']),new_delivery=dict(id=new_deliveries[0]['id'],target=new_deliveries[0]['entry']['target'],semantics=new_deliveries[0]['delivery_semantics']),later_received_buffer_available=False,reason='The Page buffer was not serialized on moved-close failure. Its variable name in printed source is not a capture. Only panel-after returned one real revision/ID record.',conclusion='No evidence distinguishes transient host revision, missed observation, later revision, or no matching response. Do not assert the transient-projection hypothesis or a product defect.'),next_predicate_proposal=dict(execution_authorized=False,match=['real GET200 with full canonical connection tuple','A canonical ID exactly once in Needs you and absent Active','current waiting_user/full with same pending request ID','new A1 succeeded delivery target matches exact operation and session','same A2 modal node and canonical request context remain unchanged','after public close, exact same A ID or stable Home heading receives focus, never B'],revision='Record actual revision; do not require equality to a prior potentially intermediate host digest',instrumentation='Persist only revision/status/full tuple/column IDs/semantic status/new target IDs in every phase result, including catch; no raw CAS/inputs',authority='Fresh own fixture, original120s lease/question limits, no renewals; publish question after setup; no provider/browser POST'))
path=HERE/'experience-consolidated-review.json';path.write_text(json.dumps(review,indent=2)+'\n')
lines=['# R8 experience qualification: conservative consolidation','',f"{review['executed_predicates_passed']} executed predicates passed. The final moved-close phase stopped before its assertions; no full-batch PASS.",'','The own process exited0 without signals and physical resources are absent. Canonical close was confirmed for3/4 sessions; the pending-question session close remained unknown. See the preserved cleanup sidecar.','','| Scenario | Assessment | Literal scope |','|---|---|---|']
lines += [f'| {k} | {v[0]} | {v[1]} |'for k,v in rows.items()]
lines += ['','The only serialized received board is the positive panel-after record. The host subsequently captured A in Needs you with current/full blocking and an exact succeeded delivery for A1, but the later browser buffer was not serialized. Equality-of-revision timeout alone does not establish a product defect or an asynchronous-projection cause.','','A future F07/I02 cut should persist the actual observer buffer and match full canonical tuple, expected membership/status/request and terminal target. It should then close through the public UI and assert same-ID focus. This is preparation only, not a new runtime authorization.','','Evidence: `experience-r8-session-role/qualification.json`, `manifest.json`, `canonical-cleanup-detail.json` and `supplement-manifest.json`. Earlier naming/oracle cuts remain unchanged.']
(HERE/'experience-consolidated-review.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(dict(review=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),passed=review['executed_predicates_passed'],active_resources=False),indent=2))
