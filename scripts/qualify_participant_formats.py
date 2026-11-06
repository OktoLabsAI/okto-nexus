"""Read generated participant configs with real clients in fresh isolated homes.

This campaign sends no model turn, imports no real credential and never approves
the Claude project MCP. It proves configuration parsing, not MCP participation.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
import threading

import nexus_connector_core
from nexus_connector_core.participant_config import participant_client_config, plan_participant_config
from nexus_connector_core.config_persistence import apply_json_plan_file, apply_toml_plan_file


def run(directory, executables):
    root = Path(directory).resolve()
    root.mkdir()  # Refuse any reused/personal campaign directory.
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(401)
            self.end_headers()
        do_POST = do_GET
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    report = dict(scope='real_client_configuration_read_only', core_module=nexus_connector_core.__file__, cases=[], model_turns=0,
        real_credentials=False, mcp_negotiated=False, participant_session_proven=False)
    try:
        for client, executable in executables.items():
            home = root / client
            project = home / 'project with espaços'
            for child in (project, home / 'codex', home / 'claude', home / 'roaming', home / 'local'):
                child.mkdir(parents=True)
            child_env = {key: value for key, value in os.environ.items()
                if key.upper() in {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATH', 'TEMP', 'TMP', 'PATHEXT'}}
            child_env.update(HOME=str(home), USERPROFILE=str(home), APPDATA=str(home / 'roaming'),
                LOCALAPPDATA=str(home / 'local'), CODEX_HOME=str(home / 'codex'),
                CLAUDE_CONFIG_DIR=str(home / 'claude'), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
                DISABLE_AUTOUPDATER='1', DISABLE_TELEMETRY='1', NO_COLOR='1')
            def command(arguments):
                result = subprocess.run(['rtk', 'proxy', str(executable), *arguments], env=child_env,
                    cwd=project, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
                return dict(args=arguments, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr)
            version = command(['--version'])
            assert version['exit_code'] == 0, version
            build = re.search(r'\d+\.\d+\.\d+', version['stdout']).group()
            config = participant_client_config(client=client, client_version=build,
                server_url=origin + '/mcp', approved_origin=origin, entry_name='nexus-campaign',
                credential_environment='NEXUS_PARTICIPANT_TOKEN_CAMPAIGN',
                file_scope='project' if client == 'claude' else 'user', loopback_reachable=True)
            path = project / '.mcp.json' if client == 'claude' else home / 'codex/config.toml'
            source = (b'{"mcpServers":{},"campaign_note":"preserve"}\n' if client == 'claude'
                else b'# keep unrelated preferences\nmodel = "campaign-unused"\n')
            path.write_bytes(source)
            plan = plan_participant_config(source, config)
            apply = apply_json_plan_file if client == 'claude' else apply_toml_plan_file
            applied = apply(plan, path)
            assert applied.backup_path.read_bytes() == source
            expected = path.read_bytes()
            args = ['mcp', 'get', config.entry_name] + (['--json'] if client == 'codex' else [])
            observed = command(args)
            assert observed['exit_code'] == 0, observed
            if client == 'codex':
                parsed = json.loads(observed['stdout'])
                assert parsed['transport']['url'] == config.server_url, parsed
                assert parsed['transport']['bearer_token_env_var'] == config.credential_environment, parsed
            else:
                assert config.server_url in observed['stdout'], observed
                assert 'Pending approval' in observed['stdout'], observed
            assert path.read_bytes() == expected
            assert not requests, requests
            report['cases'].append(dict(client=client, version=build, version_command=version,
                read_command=observed, config_unchanged=True, backup_matches=True,
                generated_config_sha256=hashlib.sha256(expected).hexdigest(),
                credential_resolution='NOT_PROVEN', reload_or_project_approval_required=True))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        report['mcp_http_requests'] = len(requests)
        (root / 'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--claude-executable', type=Path, required=True)
    parser.add_argument('--codex-executable', type=Path, required=True)
    args = parser.parse_args()
    run(args.directory, dict(claude=args.claude_executable.resolve(strict=True),
                            codex=args.codex_executable.resolve(strict=True)))
