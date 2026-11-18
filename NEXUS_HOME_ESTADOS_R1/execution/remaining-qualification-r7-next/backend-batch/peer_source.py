"""Build inert protocol controls. This module never launches a subprocess.

All gate paths must be in the fixture-owned directory. A gate delays only the
synthetic peer's output; it does not edit leases, grants, clocks or receipts.
"""
import ast
from pathlib import Path

def source(base:str,control:Path)->str:
    control=control.resolve()
    assert control.name=='control' and control.parent.name.startswith('nexus-hst-')
    declaration='_hst_waits = {}\n_hst_replies = {}\n'
    assert base.count('_thread_counter = 0')==1
    result=base.replace('_thread_counter = 0',declaration+'_thread_counter = 0')
    marker='    if "TRIGGER_HOLD" in text:'
    block='''    if text.startswith("HST:"):
        cfg = json.loads(text[4:])
        terminal_status = cfg.get("terminal_status", "completed")
        if terminal_status not in ("completed", "failed"):
            raise ValueError("Unsupported fixture terminal status")
        if not isinstance(cfg.get("gate"), str) or cfg["gate"] in ("", ".", "..") or any(c in cfg["gate"] for c in ("/", "\\\\", ":")):
            raise ValueError("Fixture gate must be a basename")
        gate = os.path.join(CONTROL_ROOT, cfg["gate"])
        deadline = time.monotonic() + 150
        if cfg.get("question"):
            key = 10000 + int(turn_id.rsplit("_", 1)[1])
            _hst_waits[key] = threading.Event()
            write_msg({"jsonrpc":"2.0","id":key,"method":"item/tool/requestUserInput","params":{
                "threadId":thread_id,"turnId":turn_id,"itemId":"hst-question-"+turn_id,"isBlocking":cfg["blocking"],
                "questions":[{"id":"format","header":"Format","question":"Choose fixture output format",
                    "isOther":False,"isSecret":False,"options":[{"label":"text","description":"Fixture only"}]}]}})
            while not _hst_waits[key].wait(.05):
                if time.monotonic() >= deadline: return
        while not os.path.exists(gate):
            if time.monotonic() >= deadline: return
            time.sleep(.05)
        text = cfg.get("message", "HST fixture output")

'''
    assert result.count(marker)==1
    result=result.replace(marker,block+marker)
    signature='def handle_turn(thread_id, turn_id, text, req_id):\n'
    assert result.count(signature)==1
    result=result.replace(signature,signature+'    terminal_status = "completed"\n')
    assert result.count('"status": "completed"')==1
    result=result.replace('"status": "completed"','"status": terminal_status')
    response='            log({"response_to_server_request": msg})'
    assert result.count(response)==1
    result=result.replace(response,response+'\n            key = msg.get("id")\n            if key in _hst_waits:\n                _hst_replies[key] = msg\n                _hst_waits[key].set()')
    # Managed prompts may contain execution capability material. Never echo
    # prompt text; only expose a non-secret marker derived from this peer owner.
    terminal='    item_id = "item_" + turn_id'
    assert result.count(terminal)==1
    result=result.replace(terminal,'    text = "HST synthetic output " + os.environ.get("HST_SESSION_ID", "unknown")\n'+terminal)
    result='CONTROL_ROOT='+repr(str(control))+'\n'+result
    ast.parse(result)
    return result
