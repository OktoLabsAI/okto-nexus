"""Real loopback SSE -> production HomeController -> real Home GET.

The two owned processes use a migrated disposable SQLite home and no lifespan,
runtime, harness discovery or credential. Only the parent fixture's pipe can
write synthetic records; all HTTP mutation methods are refused.
"""
import asyncio
import json
import multiprocessing
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace

import httpx


def _serve_fixture(channel, home):
    import uvicorn
    from fastapi.responses import JSONResponse
    from okto_nexus.bootstrap import dependencies, embedded_inventory
    from okto_nexus.adapters.inbound.http.app import build_app

    embedded_inventory.discover_local_candidates = lambda **_: SimpleNamespace(candidates=())
    deps = dependencies.bootstrap({}, ['--home', home, '--feature-harness-integrations', 'false',
                                       '--embedding-mode', 'off'])
    with deps.connection_factory.unit_of_work() as uow:
        deps.repos.workspaces.upsert(uow, workspace_id='stream-fixture')
        deps.repos.agents.upsert(uow, agent_id='stream-worker', role='worker')
    app = build_app(deps)
    app.state.sse_poll_seconds = .025
    app.state.sse_ping_seconds = .1

    @app.middleware('http')
    async def read_only(request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            return JSONResponse({'fixture': 'read-only'}, status_code=405)
        return await call_next(request)

    def commit(number, prune):
        now = deps.clock.now_iso()
        with deps.connection_factory.unit_of_work() as uow:
            c = uow.connection
            c.execute("INSERT INTO tasks(task_id,workspace_id,title,status,created_by,created_at) "
                      "VALUES(?,'stream-fixture',?,'OPEN','stream-worker',?)",
                      (f'task-{number}', f'Boundary item {number}', now))
            c.execute("INSERT INTO handoffs(handoff_id,workspace_id,task_id,from_agent_id,target,visibility,status,created_at,updated_at) "
                      "VALUES(?,'stream-fixture',?,'stream-worker',?,'eligible','OPEN',?,?)",
                      (f'handoff-{number}', f'task-{number}',
                       json.dumps({'strategy': 'direct', 'agent_id': 'stream-worker'}), now, now))
            last = deps.event_emitter.emit(uow, workspace_id='stream-fixture', stream='workspace',
                type='handoff.created', actor_agent_id='stream-worker', visibility='public',
                payload={'handoff_id': f'handoff-{number}'})
            if prune:
                # Retention changes the real journal; keep AUTOINCREMENT high-water.
                c.execute('DELETE FROM events WHERE event_id < ?', (last,))
        return last

    async def serve():
        config = uvicorn.Config(app, host='127.0.0.1', port=0, lifespan='off', log_level='error',
                                timeout_graceful_shutdown=3)
        server = uvicorn.Server(config)
        app.state.server = server
        sock = config.bind_socket()
        task = asyncio.create_task(server.serve(sockets=[sock]))
        deadline = time.monotonic() + 90
        try:
            while not server.started:
                if task.done():
                    await task
                    raise AssertionError('fixture server did not start')
                await asyncio.sleep(.01)
            channel.send({'ready': True, 'port': sock.getsockname()[1], 'runtime_started': False})
            while time.monotonic() < deadline:
                if channel.poll():
                    command = channel.recv()
                    if command['action'] == 'stop':
                        return
                    assert command['action'] == 'commit'
                    channel.send({'cursor': commit(command['number'], command.get('prune', False))})
                await asyncio.sleep(.01)
            raise AssertionError('fixture lifetime exceeded')
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 8)
            sock.close()
    try:
        asyncio.run(serve())
    finally:
        deps.connection_factory.close()
        channel.close()


NODE_CLIENT = r"""
import readline from 'node:readline';
import { pathToFileURL } from 'node:url';
const { moduleURL } = await import(pathToFileURL(process.argv[2]).href);
const { HomeController } = await import(await moduleURL('homeController.ts'));
const base = process.argv[1];
const output = value => process.stdout.write(JSON.stringify(value) + '\n');
let calls = 0, active = 0, peak = 0;
const api = {overview: async (filters, signal) => {
  calls++; active++; peak = Math.max(peak, active);
  try {
    const response = await fetch(base + '/api/v1/home/overview?' + new URLSearchParams(filters), {signal});
    if (!response.ok) throw new Error('OVERVIEW_HTTP_' + response.status);
    return (await response.json()).data;
  } finally { active--; }
}};
const controller = new HomeController({api, now: () => performance.now(),
  setTimeout: (fn, delay) => setTimeout(fn, delay), clearTimeout});
async function until(predicate) {
  const end = performance.now() + 8000;
  while (!predicate()) {
    if (performance.now() > end) throw new Error('FIXTURE_TIMEOUT');
    await new Promise(resolve => setTimeout(resolve, 10));
  }
}
function projection() {
  const snapshot = controller.getState().snapshot;
  return {cursor: snapshot.event_cursor, low: snapshot.event_low_watermark,
    titles: snapshot.work.items.map(x => x.title), total: snapshot.work.total, calls, peak};
}
controller.configure({workspace: 'stream-fixture', identityKey: 'synthetic-loopback', origin: base, visible: true, enabled: true});
await until(() => controller.getState().snapshot && !controller.getState().loading);
output({stage: 'initial', ...projection()});
const input = readline.createInterface({input: process.stdin});
try {
  for await (const line of input) {
    const command = JSON.parse(line);
    if (command.action === 'stop') break;
    const before = calls;
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 8000);
    let frame;
    try {
      const response = await fetch(base + '/api/v1/stream?view=attention&workspace=stream-fixture',
        {headers: {'Last-Event-ID': String(command.after)}, signal: abort.signal});
      if (!response.ok || !response.headers.get('content-type').startsWith('text/event-stream')) throw new Error('SSE_HTTP_REFUSED');
      const reader = response.body.getReader(), decoder = new TextDecoder();
      let body = '';
      while (!body.includes('\n\n')) {
        const chunk = await reader.read();
        if (chunk.done) throw new Error('SSE_ENDED_WITHOUT_RESET');
        body += decoder.decode(chunk.value, {stream: true}).replaceAll('\r\n', '\n');
        if (body.length > 8192) throw new Error('SSE_FRAME_TOO_LARGE');
      }
      const fields = Object.fromEntries(body.split('\n\n')[0].split('\n').map(row => {
        const at = row.indexOf(':'); return [row.slice(0, at), row.slice(at + 1).trim()];
      }));
      frame = {event: fields.event, id: Number(fields.id), data: JSON.parse(fields.data)};
      await reader.cancel();
    } finally { clearTimeout(timer); abort.abort(); }
    // These are the production hook's public controller inputs. No fake API
    // response, manual state patch or mirror projection bridges the boundary.
    controller.onStreamStatus('live');
    controller.invalidate({type: frame.event, event_id: frame.id});
    await until(() => calls > before && !controller.getState().loading &&
      controller.getState().snapshot.event_cursor >= command.expected);
    output({stage: command.stage, frame, ...projection()});
  }
} catch (error) {
  output({error: error.name, code: error.message}); process.exitCode = 1;
} finally { controller.dispose(); input.close(); }
"""


def test_commit_subscription_reconnect_and_retention_gap_refresh_real_home(tmp_path, record_property):
    root = Path(__file__).resolve().parents[2]
    node = shutil.which('node')
    assert node, 'The existing frontend Node toolchain is required'
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    server = context.Process(target=_serve_fixture, args=(child, str(tmp_path/'home')))
    server.start()
    child.close()
    client = None
    reader = None
    stderr = (tmp_path/'client.stderr').open('w', encoding='utf-8')
    outputs = queue.Queue()
    records = []

    def recv_control():
        assert parent.poll(20), 'fixture control response timed out'
        return parent.recv()

    def next_output():
        value = outputs.get(timeout=20)
        assert value is not None, 'Node client exited before its result'
        result = json.loads(value)
        assert 'error' not in result, result
        return result

    try:
        ready = recv_control()
        assert ready['ready'] and ready['runtime_started'] is False
        base = f"http://127.0.0.1:{ready['port']}"
        client = subprocess.Popen([node, '--input-type=module', '-e', NODE_CLIENT, base,
            str(root/'frontend/tests/homeR1Support.mjs')], cwd=tmp_path, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=stderr, text=True, encoding='utf-8')

        def read_output():
            for line in client.stdout:
                outputs.put(line)
            outputs.put(None)
        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        baseline = next_output()
        assert baseline['total'] == 0
        after = baseline['cursor']
        for number, stage, prune in ((1, 'commit-before-subscribe', False),
                                     (2, 'commit-while-disconnected', False),
                                     (3, 'retention-gap', True)):
            # Commit atomically after the preceding overview and before SSE.
            parent.send({'action': 'commit', 'number': number, 'prune': prune})
            cursor = recv_control()['cursor']
            assert cursor > after
            # Force a genuine retention gap by reconnecting from the original
            # snapshot cursor after old rows have been removed.
            requested = baseline['cursor'] if prune else after
            client.stdin.write(json.dumps({'action': 'stream', 'after': requested,
                                          'expected': cursor, 'stage': stage})+'\n')
            client.stdin.flush()
            result = next_output()
            assert result['frame']['event'] == 'attention-reset'
            assert result['frame']['data']['reason'] == ('retention_gap' if prune else 'snapshot_required')
            assert result['frame']['id'] == result['cursor'] == cursor
            assert result['total'] == number
            assert set(result['titles']) == {f'Boundary item {n}' for n in range(1, number+1)}
            assert result['peak'] == 1
            records.append(result)
            after = cursor
        assert records[-1]['low'] > baseline['cursor']
        with httpx.Client(base_url=base, trust_env=False, timeout=5) as http:
            assert http.post('/api/v1/home/overview', json={}).status_code == 405
    finally:
        if client is not None:
            if client.poll() is None:
                try:
                    client.stdin.write('{"action":"stop"}\n')
                    client.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            client.wait(timeout=15)
            if reader:
                reader.join(timeout=2)
            client.stdin.close()
            client.stdout.close()
        if server.is_alive():
            parent.send({'action': 'stop'})
        server.join(timeout=15)
        parent.close()
        stderr.close()
        assert not server.is_alive(), 'owned fixture server must physically exit'
        assert server.exitcode == 0
        assert client is None or client.returncode == 0
        record_property('boundary_evidence', json.dumps({'server_pid': server.pid,
            'server_exit_code': server.exitcode, 'client_pid': client.pid if client else None,
            'client_exit_code': client.returncode if client else None, 'runtime_started': False,
            'provider_calls': 0, 'real_authentication': False, 'phases': records}))
