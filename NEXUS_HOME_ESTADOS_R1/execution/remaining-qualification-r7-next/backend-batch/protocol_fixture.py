import asyncio
import json
import sys
import time

def install_native(connected, source, *, environment=None):
    from nexus_connector_core import CoreError
    from nexus_connector_core.models import EffectRejected
    from nexus_connector_core.native.adapters.codex import CodexAppServerConnector
    from nexus_connector_core.native.adapter_types import NativeAdapterError
    from nexus_connector_core.native.runtime_bridge import CopiedAdapterSession
    from nexus_connector_core.native.redaction import NativeSecretRedactor, credential_values
    setup, binding, _ = connected
    _, app, _, _, *_, root = setup
    peers = []
    log = root / "native-wire.jsonl"
    # The legacy fake predates the Core's mandatory read-only account handshake.
    # This is an explicitly unauthenticated synthetic peer, never a real login.
    marker = '        elif method == "thread/start":\n'
    if marker in source and 'elif method == "account/read":' not in source:
        added = (
            '        elif method == "account/read":\n'
            '            write_msg({"jsonrpc":"2.0","id":req_id,"result":{"requiresOpenaiAuth":False,"account":None}})\n'
        )
        if 'elif method == "initialized":' not in source:
            added = '        elif method == "initialized":\n            continue\n' + added
        source = source.replace(marker, added + marker, 1)

    class Factory:
        async def open(self, prepared, session_id, context, *, stream_epoch,
                       opening_guard=None, process_birth_recorder=None, process_launch=None):
            peer = CodexAppServerConnector(command=[sys._base_executable, "-u", "-c", source, str(log)],
                cwd=str(root), env={**(environment or {}), 'HST_SESSION_ID': session_id})
            peer.native_approvals_enabled = True
            peers.append(peer)
            def guard(stage='fixture_open'):
                probe = getattr(opening_guard, 'context_probe', None)
                current = probe() if probe is not None else context
                if opening_guard is not None and opening_guard.closed:
                    raise CoreError('RUNTIME_DRAINING', stage, retry_safe=True)
                if time.monotonic() >= current.lease_deadline_monotonic:
                    raise CoreError('AGENT_REVOKED', stage, retry_safe=True)

            if process_launch is not None:
                identity = process_launch.identity
                assert (identity.key.server_id, identity.key.executor_id, identity.key.session_id) == (
                    context.server_id, context.executor_id, session_id)
                peer._process_container_id = identity.container_id
            peer._launch_guard = guard
            if process_birth_recorder is not None:
                loop = asyncio.get_running_loop()
                def record(evidence):
                    pending = process_birth_recorder(evidence)
                    recorded = asyncio.run_coroutine_threadsafe(pending, loop)
                    recorded.result(timeout=5)
                    guard('fixture_process_birth')
                peer._process_birth_observer = record

            def start():
                guard()
                return peer.start(owning_agent_id=context.agent_id)

            try:
                if process_launch is None:
                    native = await asyncio.to_thread(start)
                else:
                    native = await process_launch.produce(validate_authority=guard, start=start)
            except BaseException as error:
                stopped = await asyncio.to_thread(peer.close)
                if isinstance(error, NativeAdapterError) and stopped in ('graceful', 'forced', 'already_closed'):
                    raise EffectRejected('Synthetic native startup failed and its owned process stopped.',
                        failure_code='NATIVE_PROTOCOL_INCOMPATIBLE' if error.details.get('reason') == 'protocol_incompatible'
                        else 'NATIVE_STARTUP_FAILED') from error
                raise
            return CopiedAdapterSession(peer, native, session_id=session_id, stream_epoch=stream_epoch, context=context,
                redactor=NativeSecretRedactor(credential_values(environment or {})))
    app.state.embedded_dispatch_owner.native_factory = Factory()
    return peers, log

BASE_SOURCE='\nimport json\nimport os\nimport sys\nimport threading\nimport time\n\nLOG_PATH = sys.argv[1] if len(sys.argv) > 1 else None\n_write_lock = threading.Lock()\n_log_lock = threading.Lock()\n_counter_lock = threading.Lock()\n_thread_counter = 0\n_turn_counter = 0\n\n\ndef write_msg(obj):\n    with _write_lock:\n        sys.stdout.write(json.dumps(obj) + "\\n")\n        sys.stdout.flush()\n\n\ndef log(entry):\n    if not LOG_PATH:\n        return\n    with _log_lock:\n        with open(LOG_PATH, "a", encoding="utf-8") as fh:\n            fh.write(json.dumps(entry) + "\\n")\n\n\ndef next_thread_id():\n    global _thread_counter\n    with _counter_lock:\n        _thread_counter += 1\n        return "th_%d" % _thread_counter\n\n\ndef next_turn_id():\n    global _turn_counter\n    with _counter_lock:\n        _turn_counter += 1\n        return "turn_%d" % _turn_counter\n\n\ndef handle_turn(thread_id, turn_id, text, req_id):\n    if "TRIGGER_ERROR" in text:\n        write_msg({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32000, "message": "boom"}})\n        return\n\n    write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"turn": {"id": turn_id, "status": "inProgress"}}})\n    write_msg({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress"}}})\n\n    if "TRIGGER_SERVER_REQUEST" in text:\n        # Live-verified real ServerRequest method name (codex app-server\n        # generate-json-schema + a live probe against 0.144.6/LAN box,\n        # 2026-09-20): "item/tool/call" is not a real ServerRequest method -\n        # the real ones are item/commandExecution/requestApproval,\n        # item/fileChange/requestApproval, item/tool/requestUserInput, etc.\n        # Harmless either way (this connector\'s reply_method_not_found does\n        # not branch on the method name - any id+method combo gets -32601),\n        # but corrected for fidelity to the real wire shape.\n        write_msg({"jsonrpc": "2.0", "id": 9001, "method": "item/commandExecution/requestApproval", "params": {}})\n\n    if "TRIGGER_MALFORMED" in text:\n        with _write_lock:\n            sys.stdout.write("not-json-garbage\\n")\n            sys.stdout.flush()\n\n    if "TRIGGER_EMPTY_METHOD" in text:\n        # JSON-RPC-legal (parses fine) but domain-invalid: HarnessEvent\n        # rejects an empty native_event. Reproduces the reader-thread wedge\n        # class distinct from TRIGGER_MALFORMED\'s JSONDecodeError.\n        write_msg({"method": "", "params": {}})\n\n    if "TRIGGER_ARRAY_PARAMS" in text:\n        # JSON-RPC 2.0 explicitly permits "params" as an array. This\n        # connector\'s _extract_thread_id calls params.get(...), which\n        # raises AttributeError on a list - the second reader-thread-wedge\n        # trigger shape.\n        write_msg({"method": "item/started", "params": ["not", "a", "dict"]})\n\n    if "TRIGGER_CRASH" in text:\n        time.sleep(0.05)\n        os._exit(7)\n\n    if "TRIGGER_HOLD" in text:\n        return\n\n    if "TRIGGER_DELAYED_COMPLETE" in text:\n        # A deliberate pause between turn/started and the rest of the turn\'s\n        # events, wide enough for a test to reliably call end() WHILE the\n        # turn is still in flight (i.e. before turn/completed is even\n        # written) rather than racing a turn that completes near-instantly.\n        time.sleep(0.3)\n\n    item_id = "item_" + turn_id\n    write_msg({"method": "item/started", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": item_id, "type": "agentMessage"}, "startedAtMs": 0}})\n    write_msg({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": item_id, "delta": text}})\n    write_msg({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": item_id, "type": "agentMessage", "text": text}, "completedAtMs": 0}})\n    write_msg({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed"}}})\n\n\ndef main():\n    for raw in sys.stdin:\n        line = raw.strip()\n        if not line:\n            continue\n        try:\n            msg = json.loads(line)\n        except json.JSONDecodeError:\n            continue\n        method = msg.get("method")\n        req_id = msg.get("id")\n        params = msg.get("params") or {}\n\n        if method is None:\n            # A response to a request WE (the fake server) sent - e.g. the\n            # connector\'s -32601 reply to our unsolicited server-request.\n            log({"response_to_server_request": msg})\n            continue\n\n        if method == "initialize":\n            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"userAgent": "okto-nexus/0.156.1"}})\n        elif method == "thread/start":\n            thread_id = next_thread_id()\n            if params.get("_early_notify"):\n                write_msg({"method": "thread/started", "params": {"thread": {"id": thread_id}}})\n            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"thread": {"id": thread_id}}})\n        elif method == "turn/start":\n            log({"method": "turn/start", "params": params})\n            thread_id = params["threadId"]\n            text = params["input"][0]["text"]\n            turn_id = next_turn_id()\n            threading.Thread(target=handle_turn, args=(thread_id, turn_id, text, req_id), daemon=True).start()\n        elif method == "turn/steer":\n            log({"method": "turn/steer", "params": params})\n            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {}})\n        elif method == "turn/interrupt":\n            log({"method": "turn/interrupt", "params": params})\n            # RES-C2 fix: real capture (EV-CX-001-raw_capture_interrupt.jsonl,\n            # live-verified against codex 0.144.6/.152) shows the RPC result\n            # and turn/completed(status="interrupted") arrive TOGETHER, no\n            # separate settle notification and no delay - the fake used to\n            # ack and then emit NOTHING further, an omission that let no test\n            # observe correct-or-wrong post-interrupt ordering at all. Now\n            # matches the real wire: result first, then turn/completed with\n            # status "interrupted" for the SAME turnId, written back-to-back.\n            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {}})\n            write_msg(\n                {\n                    "method": "turn/completed",\n                    "params": {\n                        "threadId": params["threadId"],\n                        "turn": {"id": params["turnId"], "status": "interrupted"},\n                    },\n                }\n            )\n        elif method == "thread/unsubscribe":\n            log({"method": "thread/unsubscribe", "params": params})\n            # Live-verified result shape (same probe as above): the real\n            # response is {"status": "unsubscribed"}, not {"status": "ok"}.\n            # Harmless either way - this connector discards a successful\n            # fire-and-forget response entirely and never reads this field -\n            # but corrected for fidelity.\n            write_msg({"jsonrpc": "2.0", "id": req_id, "result": {"status": "unsubscribed"}})\n        else:\n            write_msg({"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "unhandled by fake server"}})\n\n\nif __name__ == "__main__":\n    main()\n'
