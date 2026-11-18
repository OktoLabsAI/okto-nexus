"""Static preparation only; creates new counterparts, never launches the fixture."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, text):
    path = HERE / name
    assert not path.exists(), path
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


base_js = (HERE / "browser-s3-reviewed.js").read_text(encoding="utf-8")
addition = r'''
    // Attach before opening: inspect the exact original approval, not a queue DTO.
    const approvalPath='/api/v1/approvals/'+encodeURIComponent(cfg.approval_id);
    const detailResponse=page.waitForResponse(response=>new URL(response.url()).pathname===approvalPath&&response.request().method()==='GET',{timeout:10000});
    await page.getByTestId('attention-open-'+cfg.attention_id).click();
    const observedDetail=await detailResponse;
    check('classic-original-approval-GET-200',observedDetail.status()===200,observedDetail.status());
    const detailRaw=await observedDetail.json(),detail=detailRaw.data??detailRaw;
    const proposal=detail.request_payload?.kwargs,key=proposal?.approval_key;
    const expected={server_id:cfg.reference.server_id,executor_id:cfg.reference.executor_id,
      agent_id:cfg.reference.agent_id,session_id:cfg.session_id,canonical_request_id:cfg.approval_id};
    check('classic-original-request-identity',detail.approval_id===cfg.approval_id&&detail.workspace_id===cfg.workspace_id&&
      Object.entries(expected).every(([name,value])=>key?.[name]===value)&&
      detail.decision_detail?.operation_id===cfg.operation_id,
      {approval_id:detail.approval_id,workspace_id:detail.workspace_id,matched_scope:Object.keys(expected),operation_matches:detail.decision_detail?.operation_id===cfg.operation_id});
    check('classic-original-request-pending',detail.status==='pending'&&detail.decision_detail?.state==='PENDING',
      {status:detail.status,state:detail.decision_detail?.state});
    const dialog=page.locator('dialog[open]');
    const native=dialog.getByRole('region',{name:'Native runtime decision',exact:true});
    await native.waitFor({state:'visible',timeout:10000});
    const choices=native.getByRole('listbox',{name:'Choose fixture output format',exact:true});
    await choices.waitFor({state:'visible',timeout:10000});
    check('classic-canonical-form-original-options',await choices.evaluate(el=>el.multiple&&el.selectedOptions.length===0&&
      Array.from(el.options).some(option=>option.textContent==='text')),true);
    const deny=native.getByRole('button',{name:'Deny runtime request',exact:true});
    const end=Date.now()+10000;
    while(!await deny.isEnabled()&&Date.now()<end)await page.waitForTimeout(50);
    check('classic-canonical-controls-accessible',await native.getByRole('button',{name:'Send answer',exact:true}).isVisible()&&
      await deny.isEnabled()&&await native.getByRole('button',{name:'Check native decision',exact:true}).isEnabled(),
      {answer_visible:true,deny_enabled:await deny.isEnabled(),recovery_read_enabled:await native.getByRole('button',{name:'Check native decision',exact:true}).isEnabled()});
    // No selection/edit/submit: the original CLI answers only after this panel closes.
    await dialog.getByRole('button',{name:'Close modal',exact:true}).click();
    await page.locator('dialog[open]').waitFor({state:'hidden',timeout:10000});
    check('classic-form-closed-without-answer',writes.length===0,writes);
'''
needle = "    check('zero-non-read-browser-requests',writes.length===0,writes);"
assert base_js.count(needle) == 1
js = base_js.replace(needle, addition + needle)
js = js.replace("'Classic Conversations navigation itself was not exercised'", "'K03 literal requires classic Home/controls/bell; Conversations navigation is not claimed'")
write("browser-s3-k03.js", js)

old_runner = (HERE / "run_s3_v2.py").read_text(encoding="utf-8")
runner = old_runner.replace("ROOT_APPROVED_COMPAT_BATCH_S3", "ROOT_APPROVED_COMPAT_K03")
runner = runner.replace("PREPARED-S3-R9-v2.json", "PREPARED-K03-R9.json")
runner = runner.replace("browser-s3-reviewed.js", "browser-s3-k03.js")
runner = runner.replace("nexus-hst-compat-s3-", "nexus-hst-compat-k03-")
needle = "'binding_id': active['binding']['binding_id'], 'attention_id': next(iter(attention_ids))}"
assert runner.count(needle) == 1
runner = runner.replace(needle, "'binding_id': active['binding']['binding_id'], 'attention_id': next(iter(attention_ids)),\n            'approval_id': active['approval_id'], 'session_id': active['session_id'],\n            'operation_id': active['operation_id'],\n            'reference': {key: active['binding'][key] for key in ('server_id', 'executor_id', 'agent_id')}}")
ast.parse(runner)
write("run_k03.py", runner)
write("K03-counterparts.diff", "".join(difflib.unified_diff(base_js.splitlines(True), js.splitlines(True), fromfile="browser-s3-reviewed.js", tofile="browser-s3-k03.js")) +
      "".join(difflib.unified_diff(old_runner.splitlines(True), runner.splitlines(True), fromfile="run_s3_v2.py", tofile="run_k03.py")))
manifest = json.loads((HERE / "PREPARED-S3-R9-v2.json").read_text(encoding="utf-8"))
manifest["requires_explicit_root_gate"] = "ROOT_APPROVED_COMPAT_K03"
manifest["journey"] = "K03 classic original controls complement; S3 invariants unchanged"
manifest["scenarios"] = ["HST-T-K03"]
manifest["antecedent_success"] = {"qualification": "attempt2-s3-r9/qualification.json", "sha256": sha(HERE / "attempt2-s3-r9/qualification.json"), "browser_checks": 13}
for name in ("browser-s3-k03.js", "run_k03.py", "K03-counterparts.diff"):
    manifest["helper_sha256"][str(HERE / name)] = sha(HERE / name)
manifest["static_checks"] = {"AST": "PASS", "runtime_started": False, "browser_started": False, "effective_browser_placeholder_count": js.count("__CONFIG__")}
manifest["limits"] += ["Prepared only; no execution. All original 13 browser predicates retained; six canonical form checks added.", "No answer, denial, form selection, Seen, Snooze or other UI write; CLI alone answers afterward.", "No Conversations navigation claimed: K03 literal asks classic Home/controls/bell.", "Original 120s request TTL, 60s CLI browser wait, 180s outer bound unchanged."]
write("PREPARED-K03-R9.json", json.dumps(manifest, indent=2) + "\n")
print(json.dumps({name: sha(HERE / name) for name in ("browser-s3-k03.js", "run_k03.py", "K03-counterparts.diff", "PREPARED-K03-R9.json")}, indent=2))
