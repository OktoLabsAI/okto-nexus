import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nexus_connector_core.participant_config import participant_client_config
from okto_nexus.adapters.outbound.participant_process import child_environment, launch_context
from okto_nexus.adapters.outbound.participant_files import file_plan, apply_file

import argparse

parser = argparse.ArgumentParser(description='Isolated participant credential resolution; no user messages or model turns.')
parser.add_argument('--claude', type=Path, required=True)
parser.add_argument('--codex', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
ROOT = args.output.resolve()
ROOT.mkdir(parents=True, exist_ok=False)
CLAUDE = args.claude.resolve(strict=True)
CODEX = args.codex.resolve(strict=True)
KEY = 'nxs_' + secrets.token_hex(24)
REF = 'NEXUS_PARTICIPANT_TOKEN_PROBE'
EVENTS = []

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, value=None):
        data = json.dumps(value).encode() if value is not None else b''
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(min(int(self.headers.get('Content-Length', 0)), 1048576))
        message = json.loads(raw) if raw else {}
        method = message.get('method')
        matched = self.headers.get('Authorization') == 'Bearer ' + KEY
        EVENTS.append(dict(path=self.path, method=method, auth_matched=matched))
        if self.path != '/mcp':
            return self.reply(503)
        if not matched:
            return self.reply(401)
        if 'id' not in message:
            return self.reply(202)
        results = {'initialize': dict(protocolVersion=message.get('params', {}).get('protocolVersion', '2025-03-26'),
            capabilities={'tools': {}}, serverInfo={'name': 'isolated-fixture', 'version': '1'}),
            'tools/list': {'tools': []}, 'resources/list': {'resources': []},
            'resources/templates/list': {'resourceTemplates': []}, 'prompts/list': {'prompts': []}, 'ping': {}}
        self.reply(200, dict(jsonrpc='2.0', id=message['id'], result=results.get(method, {})))

    def do_GET(self):
        self.reply(405)

    def do_DELETE(self):
        self.reply(200)

def run(client, origin, available):
    root = ROOT / (client + '-' + ('present-' if available else 'missing-') + secrets.token_hex(4))
    root.mkdir()
    env = {k: v for k, v in os.environ.items() if k.upper() in
        ('SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP')}
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CODEX_HOME', 'CLAUDE_CONFIG_DIR'):
        env[name] = str(root / name.lower())
        Path(env[name]).mkdir()
    env.update({'ANTHROPIC_API_KEY': 'synthetic-provider-key', 'ANTHROPIC_BASE_URL': origin + '/provider',
        'OPENAI_API_KEY': 'synthetic-provider-key', 'OPENAI_BASE_URL': origin + '/provider',
        'DISABLE_AUTOUPDATER': '1', 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1',
        'DISABLE_TELEMETRY': '1', 'CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY': '1'})
    project = root / 'project'
    project.mkdir()
    config = project / ('.mcp.json' if client == 'claude' else '.codex/config.toml')
    contract = participant_client_config(client=client, client_version=None, server_url=origin + '/mcp',
        approved_origin=origin, entry_name='nexus', credential_environment=REF, file_scope='project', loopback_reachable=True)
    plan = file_plan(str(config), contract)
    apply_file(plan, contract)
    env = child_environment(contract, KEY, env)
    if not available:
        env.pop(REF)
    context = launch_context(dict(selection={'project': str(project)}, file=plan), contract,
        str(CLAUDE if client == 'claude' else CODEX), environment=env)
    if client == 'claude':
        argv = [context['executable'], *context['arguments'], '--bare', '--strict-mcp-config', '--mcp-config', str(config),
            '-p', '--input-format', 'stream-json', '--output-format', 'stream-json', '--verbose', '--no-session-persistence']
        messages = [dict(type='control_request', request_id='init', request={'subtype': 'initialize', 'hooks': {}}),
                    dict(type='control_request', request_id='status', request={'subtype': 'mcp_status'})]
    else:
        user_config = Path(env['CODEX_HOME']) / 'config.toml'
        user_config.write_text('[projects.' + json.dumps(str(project)) + ']\ntrust_level = "trusted"\n')
        argv = [context['executable'], *context['arguments'], 'app-server', '--listen', 'stdio://']
        messages = [dict(id=1, method='initialize', params={'clientInfo': {'name': 'nexus_probe', 'version': '1'}}),
                    dict(method='initialized', params={}),
                    dict(id=2, method='thread/start', params={'cwd': str(project), 'ephemeral': True}),
                    dict(id=3, method='mcpServerStatus/list', params={})]
    out = queue.Queue()
    transcript = []
    proc = subprocess.Popen(argv, cwd=project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf8', errors='replace', shell=False)
    def read(stream, kind):
        for _ in range(200):
            line = stream.readline(1048576)
            if not line:
                break
            out.put((kind, line.replace(KEY, '[REDACTED]')))
    readers = [threading.Thread(target=read, args=(stream, kind), daemon=True)
        for stream, kind in ((proc.stdout, 'stdout'), (proc.stderr, 'stderr'))]
    for reader in readers:
        reader.start()
    start = len(EVENTS)
    try:
        thread_id = None
        for msg in messages:
            if msg.get('method') == 'mcpServerStatus/list' and thread_id:
                msg['params']['threadId'] = thread_id
            proc.stdin.write(json.dumps(msg) + '\n')
            proc.stdin.flush()
            if msg.get('method') == 'initialized':
                continue
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    kind, line = out.get(timeout=0.25)
                except queue.Empty:
                    if proc.poll() is not None:
                        break
                    continue
                transcript.append({'stream': kind, 'line': line})
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if (client == 'claude' and reply.get('response', {}).get('request_id') == msg.get('request_id')) or (
                        client == 'codex' and reply.get('id') == msg.get('id')):
                    if msg.get('method') == 'thread/start':
                        thread_id = reply.get('result', {}).get('thread', {}).get('id')
                    break
    finally:
        proc.stdin.close()
        terminated = False
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            terminated = True
            proc.terminate()
            proc.wait(timeout=5)
        for reader in readers:
            reader.join(2)
        while not out.empty():
            kind, line = out.get_nowait()
            transcript.append({'stream': kind, 'line': line})
    leaks = [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and KEY.encode() in p.read_bytes()]
    report = dict(client=client, credential_available=available, binary_sha256=hashlib.file_digest(Path(argv[0]).open('rb'), 'sha256').hexdigest(),
        argv=argv, events=EVENTS[start:], exit_code=proc.returncode, terminated=terminated,
        transcript=transcript, secret_files=leaks, inference_requested=False, root=str(root))
    target = ROOT / (client + ('-present' if available else '-missing') + '-probe.json')
    target.write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('transcript', 'argv')}, indent=2), flush=True)
    assert not leaks
    assert not any(e['path'] != '/mcp' for e in EVENTS[start:])
    assert not any(e['method'] == 'tools/call' for e in EVENTS[start:])
    assert any(e['method'] == 'initialize' and e['auth_matched'] for e in EVENTS[start:]) == available

if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for client in ('claude', 'codex'):
            for available in (True, False):
                run(client, 'http://127.0.0.1:' + str(server.server_port), available)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
