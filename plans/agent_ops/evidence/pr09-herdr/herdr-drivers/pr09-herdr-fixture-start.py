"""ONLY fixture setup. Product observer never executes these mutation commands."""
import json
import runpy

m = runpy.run_path(r'C:\Users\jpamb\AppData\Local\Temp\pr09-herdr-live.py')
root, call = m['ROOT'], m['call']
config = root / 'config.toml'
config.write_text(config.read_text(encoding='utf-8') + '\n[update]\nversion_check = false\nmanifest_check = false\n[session]\nresume_agents_on_restore = false\n', encoding='utf-8')
call('fixture-config-reload', ['server', 'reload-config'])
argv = [str(root / 'work/codex.exe'), str(root / 'work/stop-fixture-1')]
# The existing terminal is an isolated Python REPL, not a personal shell.
command = 'import subprocess; subprocess.run(' + repr(argv) + ')'
call('fixture-process-start', ['pane', 'run', 'w1:p1', command])
call('fixture-process-started', ['pane', 'process-info', '--pane', 'w1:p1'])
(root / 'live/fixture-description.json').write_text(json.dumps({
    'type': 'synthetic-process', 'source': 'work/Fixture.cs',
    'executable': 'work/codex.exe', 'is_openai_codex': False,
    'is_provider_inference': False,
    'purpose': 'Exercise Herdr fixed native process-name recognition with a benign compiled .NET process.',
    'observer_controls_fixture': False,
}, indent=2) + '\n', encoding='utf-8')
