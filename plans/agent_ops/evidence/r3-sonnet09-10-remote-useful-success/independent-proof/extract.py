from pathlib import Path
import json,sqlite3,hashlib,datetime,re,csv,io
from decimal import Decimal
HERE=Path(__file__).resolve().parent
B=Path("C:/Users/jpamb/AppData/Local/Temp/m1-v12-bundle-bldo9qy7")
U=Path("C:/Users/jpamb/AppData/Local/Temp/sonnet-after07-pending-composition-nwafe22s")
SERVER="srv_a3f134b449dbffa20c126dae6f9a8aa9"
EXECUTOR="exe_ac3fd8f5f8a35aaf344bb8aebd13be4e"
SESSION="ses_8bc0449b68998cfe91ec1a2df9319d23"
STREAM="stream_bd7b801254266ea65ca4c9542a1c0869"
OPS=("op_772cf5101f12f73b1acc75daefe6b98c","op_37e2ddb1ba2d183c899606a846396bb3")
def digest(v):return hashlib.sha256(v if isinstance(v,bytes) else v.encode()).hexdigest()
def pin(p):return {"path":str(p),"sha256":digest(p.read_bytes()),"bytes":p.stat().st_size}
def connect(p):
 c=sqlite3.connect(p.as_uri()+"?mode=ro",uri=True);c.row_factory=sqlite3.Row;c.execute("pragma query_only=on");c.create_function("public_body_sha256",1,digest);return c
def rows(c,sql,args):return [dict(x) for x in c.execute(sql,args)]
def dt(s):return datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
scope=(SERVER,EXECUTOR,SESSION,STREAM)
where="server_id=? and executor_id=? and session_id=? and stream_epoch=?"
c=connect(B/"campaign/connector-state/executor-journal.db")
try:
 initfields=["model","permissionMode","cwd","claude_code_version","session_id","per_turn_effort_active","tools","memory_paths","mcp_servers"]
 sql="select sequence,json_extract(body,'$.operation_id') operation_id,public_body_sha256(body) event_sha256,"+",".join("json_extract(body,'$.payload."+f+"') "+f for f in initfields)+" from events where "+where+" and json_extract(body,'$.native_type')='system:init'"
 inits=rows(c,sql,scope)
 for r in inits:
  tools=json.loads(r.pop("tools") or "[]");memory=json.loads(r.pop("memory_paths") or "[]");mcps=json.loads(r.pop("mcp_servers") or "[]")
  r["advertised_tool_count"]=len(tools);r["PowerShell_advertised"]="PowerShell" in tools;r["Bash_advertised"]="Bash" in tools
  r["memory_reference_count"]=len(memory);r["memory_contents_read"]=False
  r["memory_reference_metadata"]=[{"basename_kind":"CLAUDE.md" if str(v).replace("\\","/").lower().endswith("/claude.md") else "OTHER_REFERENCE","within_approved_project":str(v).replace("\\","/").casefold().startswith(str(B/"campaign/connector-project").replace("\\","/").casefold()+"/")} for v in memory]
  r["mcp_server_count"]=len(mcps);r["mcp_status_counts"]={s:sum(isinstance(x,dict) and x.get("status")==s for x in mcps) for s in ["connected","failed","pending","disabled"]}
  r["cwd_matches_reviewed"]=Path(r["cwd"])==B/"campaign/connector-project";r["effective_effort"]="UNKNOWN"
 catalog=rows(c,"select sequence,public_body_sha256(body) event_sha256,json_extract(body,'$.payload.harness_configuration.adapter_id') adapter_id,json_extract(body,'$.payload.harness_configuration.version') version,json_extract(body,'$.payload.harness_configuration.candidate_ref') candidate_ref,json_extract(body,'$.payload.harness_configuration.schema_revision') schema_revision from events where "+where+" and json_extract(body,'$.native_type')='core/harness_configuration'",scope)
 term=rows(c,"select sequence,json_extract(body,'$.operation_id') operation_id,public_body_sha256(body) event_sha256,json_extract(body,'$.payload.session_id') native_session_id,json_extract(body,'$.payload.delivery_outcome') outcome,json_extract(body,'$.payload.is_error') is_error,json_extract(body,'$.payload.duration_ms') native_reported_duration_ms,json_extract(body,'$.payload.duration_api_ms') native_reported_duration_api_ms,json_extract(body,'$.payload.usage.input_tokens') input_tokens,json_extract(body,'$.payload.usage.cache_read_input_tokens') cache_read_input_tokens,json_extract(body,'$.payload.usage.cache_creation_input_tokens') cache_creation_input_tokens,json_extract(body,'$.payload.usage.output_tokens') output_tokens,json_extract(body,'$.payload.usage.output_tokens_details.thinking_tokens') thinking_tokens_subset_output,json_extract(body,'$.payload.output_text') output_text from events where "+where+" and json_extract(body,'$.native_type')='result:success' and json_extract(body,'$.operation_id') in (?,?)",(*scope,*OPS))
 fragments=rows(c,"select sequence,json_extract(body,'$.operation_id') operation_id,json_extract(body,'$.native_type') native_type,json_extract(body,'$.payload.output_text') output_text from events where "+where+" and json_extract(body,'$.native_type') in ('result:output','result:success') and json_extract(body,'$.operation_id') in (?,?) order by sequence",(*scope,*OPS))
 for r in term:
  assert len(r["output_text"] or "")<2000
  r["total_tokens"]=sum(r[k] for k in ["input_tokens","cache_read_input_tokens","cache_creation_input_tokens","output_tokens"])
 controls=rows(c,"select sequence,json_extract(body,'$.operation_id') operation_id,public_body_sha256(body) event_sha256,json_extract(body,'$.payload.native_approval.method') method,json_extract(body,'$.payload.native_approval.params.tool_name') tool_name,json_extract(body,'$.payload.native_approval.params.subtype') subtype,json_extract(body,'$.payload.native_approval.request_hash') request_hash from events where "+where+" and json_extract(body,'$.native_type')='control_request:can_use_tool'",scope)
finally:c.close()
c=connect(B/"campaign/nexus-home/nexus.db")
try:
 ops=rows(c,"select operation_id,session_id,actor_agent_id,subject_agent_id,binding_id,workspace_id,workspace_binding_id,action,admission_state,created_at,parent_operation_id from execution_operations where server_id=? and executor_id=? and session_id=? and operation_id in (?,?)",(SERVER,EXECUTOR,SESSION,*OPS))
 receipts=rows(c,"select operation_id,receipt_revision,stage,possible_effect,retry_safe,error_code,received_at from execution_receipts where server_id=? and executor_id=? and operation_id in (?,?) order by operation_id,receipt_revision",(SERVER,EXECUTOR,*OPS))
 results=rows(c,"select operation_id,session_id,stream_epoch,terminal_sequence,output_text,output_truncated,output_event_count,delivery_outcome,captured_at from execution_results where server_id=? and executor_id=? and session_id=? and operation_id in (?,?)",(SERVER,EXECUTOR,SESSION,*OPS))
 requests=rows(c,"select canonical_request_id,source_operation_id,session_id,stream_epoch,session_owner_generation,kind,request_revision,state,received_at,expires_at from execution_native_requests where server_id=? and executor_id=? and session_id=? and source_operation_id in (?,?)",(SERVER,EXECUTOR,SESSION,*OPS))
 decisions=rows(c,"select decision_id,canonical_request_id,session_id,session_owner_generation,kind,revision,actor_agent_id,decision,canonical_state,native_operation_id,expires_at from execution_decisions where server_id=? and executor_id=? and session_id=?",(SERVER,EXECUTOR,SESSION))
 approval=[]
 for r in requests:approval+=rows(c,"select approval_id,status,decided_by,decision_revision,created_at,decided_at from approvals where approval_id=?",(r["canonical_request_id"],))
finally:c.close()
assert len(inits)==2 and len(term)==2 and len(results)==2 and len(ops)==2
assert len(requests)==len(decisions)==1 and decisions[0]["canonical_state"]=="CONFIRMED" and decisions[0]["actor_agent_id"]=="operator"
assert decisions[0]["canonical_request_id"]==requests[0]["canonical_request_id"]
for r in results:
 assert len(r["output_text"])<2000 and not r["output_truncated"]
 native=next(x for x in term if x["operation_id"]==r["operation_id"])
 r["native_output_equal"]="".join(x["output_text"] or "" for x in fragments if x["operation_id"]==r["operation_id"])==r["output_text"]
 r["native_output_fragment_sequences"]=[x["sequence"] for x in fragments if x["operation_id"]==r["operation_id"]]
 assert r["native_output_equal"]
report=B/"campaign/deliverables/remote/report.json";reportdata=json.loads(report.read_text(encoding="utf-8"));assert set(reportdata)=={"row_count","sum","input_sha256"}
fixture=B/"campaign/connector-project/numbers.csv"
raw=fixture.read_bytes(); parsed=list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
assert len(parsed)==4
values=[Decimal(v) for row in parsed for v in row.values() if v is not None and v.strip()]
assert Decimal(str(reportdata["sum"]))==sum(values) and reportdata["row_count"]==len(parsed) and reportdata["input_sha256"]==digest(raw)
review=Path("C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t/public/recovery02-review.json")
reviewed=json.loads(review.read_text())["review"]["draft"]["configuration"]
timings=[]
for o in ops:
 terminal=next(x for x in receipts if x["operation_id"]==o["operation_id"] and x["stage"]=="SUCCEEDED")
 timings.append({"operation_id":o["operation_id"],"server_created_at":o["created_at"],"server_succeeded_receipt_at":terminal["received_at"],"server_observed_wall_seconds":(dt(terminal["received_at"])-dt(o["created_at"])).total_seconds(),"scope":"Server timestamps include admission/dispatch/native work/operator wait/transport; not pure model latency or cross-process monotonic timing."})
data={"status":"ACTUAL09_10_METADATA_AND_SYNTHETIC_RESULT_RECONCILED","observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"scope":{"server_id":SERVER,"executor_id":EXECUTOR,"session_id":SESSION,"stream_epoch":STREAM,"operation_ids":OPS},"method":"Two own SQLite databases mode=ro/query_only; exact scope/IDs; explicit columns/json_extract. Separate reads, no cross-database atomic snapshot claim. No credentials/auth/vault/personal instruction or raw command/payload exported.","configuration":{"reviewed":reviewed,"reviewed_pin":pin(review),"catalog":catalog,"catalog_scope":"Installed Claude configuration_probe obtains --help capability catalog, not session-effective state.","actual_system_init":inits,"instructions_limit":"Only native memory reference count/classification retained; personal contents never opened. Reviewed own task prompt/preset refs do not establish universal instruction adherence.","missing_fields":"Effective effort not emitted; remains UNKNOWN, reviewed default selected."},"canonical_operations":ops,"canonical_receipts":receipts,"canonical_results":results,"native_terminals":term,"native_permission_requests":requests,"native_tool_metadata":controls,"canonical_decisions":decisions,"approvals":approval,"report":{"pin":pin(report),"json":reportdata,"input_pin":pin(fixture),"independent_Decimal_validation":{"row_count":len(parsed),"sum":str(sum(values)),"report_matches":True},"root_independent_validation_tool":"15b025","same_native_session":len({x["session_id"] for x in inits})==1},"timings":timings,"accounting":{"prior_tokens":180426,"useful09":next(x["total_tokens"] for x in term if x["operation_id"]==OPS[0]),"continuation10":next(x["total_tokens"] for x in term if x["operation_id"]==OPS[1]),"cumulative":180426+sum(x["total_tokens"] for x in term),"native_charged":5,"server_charged":6,"native_limit":5,"server_limit":6,"selected_admissions_exhausted":True,"token_limit":500000,"preventive_token_limit":480000,"token_headroom_is_not_new_admission_authority":True,"thinking_is_output_subset":True,"usage_not_double_counted":True},"source_pins":{"work_plan":pin(U/"work-plan.json"),"task_prompts":pin(U/"task-prompts.json"),"useful_result":pin(U/"paid-work/public/m1-sonnet-remote-useful-09-result.json"),"continuation_result":pin(U/"paid-work/public/m1-sonnet-remote-continuation-10-result.json")},"effects":{"database_writes":0,"api_or_control":0,"provider_calls":0,"service_calls":0,"os_events":0},"extractor_antecedent":{"initial_assertion":"Comparing only result:success fragment to aggregated canonical output failed before publication.","correction":"Compare ordered result:output plus result:success output_text fragments for the exact operation; no journal or canonical result modified."},"limitations":["Native-reported duration_api_ms may use a different accumulation scope; not added to duration_ms or interpreted as per-operation wall latency.","No shutdown/physical-exit proof is inferred here; Root owns normal cleanup separately.","Synthetic task assistant output retained by explicit authorization; no personal conversation or tool-command content retained."]}
(HERE/"projection.json").write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
(HERE/"public-allowlist.json").write_text(json.dumps({"files":[{"path":p.name,"sha256":digest(p.read_bytes()),"bytes":p.stat().st_size} for p in [HERE/"extract.py",HERE/"projection.json"]]},indent=2)+"\n",encoding="utf-8")
print(json.dumps({"projection":pin(HERE/"projection.json"),"allowlist":pin(HERE/"public-allowlist.json"),"accounting":data["accounting"],"timings":timings,"configuration_native_summary":[{k:r[k] for k in ["model","permissionMode","claude_code_version","cwd_matches_reviewed","memory_reference_count","mcp_server_count","PowerShell_advertised","effective_effort"]} for r in inits]}))
