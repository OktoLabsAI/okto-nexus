"""Finite AC08 parser/help inspection; never execute a productive command."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path(__file__).parent
PYTHON = Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr/venv/Scripts/python.exe')
profile = ROOT / 'isolated-profile'
profile.mkdir(exist_ok=True)
env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT') if key in os.environ}
env.update(USERPROFILE=str(profile), APPDATA=str(profile / 'roaming'), LOCALAPPDATA=str(profile / 'local'),
           TEMP=str(profile), TMP=str(profile), PATH=str(PYTHON.parent), PYTHONUTF8='1', NO_COLOR='1')
guard = '''
import sys
def guard(event, args):
    if event in {'socket.connect','socket.bind','subprocess.Popen','os.system'}:
        raise RuntimeError('AC08_FORBIDDEN_EFFECT')
sys.addaudithook(guard)
'''
commands = [('connect',), ('init',), ('work',), ('participant','launch'),
            ('participant','remove'), ('participant','smoke'), ('message',), ('handoff',),
            ('request',), ('doctor',)]
reports = []
for command in commands:
    code = guard + '\nfrom okto_nexus.adapters.inbound.cli.main import main\nraise SystemExit(main(' + repr([*command, '--help']) + '))\n'
    result = subprocess.run([str(PYTHON), '-I', '-B', '-c', code], cwd=ROOT, env=env,
                            capture_output=True, timeout=30)
    stem = 'nexus-' + '-'.join(command)
    (ROOT / (stem + '.stdout.txt')).write_bytes(result.stdout)
    (ROOT / (stem + '.stderr.txt')).write_bytes(result.stderr)
    reports.append({'command': ['okto-nexus', *command, '--help'], 'exit_code': result.returncode,
                    'stdout': stem + '.stdout.txt', 'stderr': stem + '.stderr.txt'})

code = guard + '''
import argparse, hashlib, importlib.metadata as metadata, json
from pathlib import Path
from okto_nexus_connector.cli.main import build_parser
import nexus_connector_core, okto_nexus, okto_nexus_connector
root = Path.cwd()
expected = Path(sys.prefix) / 'Lib' / 'site-packages'
loaded = {name: str(Path(module.__file__).resolve()) for name, module in tuple(sys.modules.items())
          if name.split('.')[0] in {'nexus_connector_core','okto_nexus','okto_nexus_connector'}
          and getattr(module, '__file__', None)}
assert all(Path(path).is_relative_to(expected) for path in loaded.values())
lines = ['# CLI syntax reference', '',
    'Generated from the CLI parser. Regenerate with `python tools/generate_cli_reference.py`.', '',
    'Read the [usage guide](cli.md) for effects and prerequisites. --json and --verbose work before or after any command; other global options go before the command. Uppercase values are placeholders. Brackets mean optional; unbracketed flags are required. Legacy syntax is not proof of R4 support.', '']
parsers = {}
def walk(parser, name):
    help_text = parser.format_help().rstrip()
    parsers[name] = help_text
    lines.extend(['## ' + name, '', '```text', help_text, '```', ''])
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for command, child in action.choices.items():
                walk(child, name + ' ' + command)
walk(build_parser(), 'okto-nexus-connector')
(root / 'connector-cli-reference.current.md').write_text('\\n'.join(lines), encoding='utf-8')
(root / 'connector-parser-help.json').write_text(json.dumps(parsers, indent=2) + '\\n', encoding='utf-8')
(root / 'installed-import-proof.json').write_text(json.dumps({
    'versions': {d:metadata.version(d) for d in ('okto-nexus','okto-nexus-connector','okto-nexus-connector-core')},
    'all_project_modules_inside_selected_venv':True,
    'modules': {name: {'file': path,'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()} for name,path in loaded.items()},
    'connector_parser_count':len(parsers)},indent=2) + '\\n',encoding='utf-8')
'''
result = subprocess.run([str(PYTHON), '-I', '-B', '-c', code], cwd=ROOT, env=env,
                        capture_output=True, timeout=30)
(ROOT / 'parser-import.stdout.txt').write_bytes(result.stdout)
(ROOT / 'parser-import.stderr.txt').write_bytes(result.stderr)
reports.append({'command': ['isolated import and parser.format_help only'], 'exit_code': result.returncode,
                'stdout': 'parser-import.stdout.txt', 'stderr':'parser-import.stderr.txt'})
for report in reports:
    for key in ('stdout', 'stderr'):
        report[key + '_sha256'] = hashlib.sha256((ROOT / report[key]).read_bytes()).hexdigest()
(ROOT / 'help-checks.json').write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'checks':len(reports),'nonzero':sum(r['exit_code'] != 0 for r in reports)}))
