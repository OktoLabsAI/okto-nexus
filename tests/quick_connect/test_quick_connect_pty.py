"""Run explicitly in an agent-owned real input PTY with pytest -s.

No stdin/isatty/input monkeypatch. Never provider qualification: only the
canonical temporary HTTP/SQLite fixture and synthetic check/Test peers.
"""
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
import sys
from types import SimpleNamespace

import pytest

import test_quick_connect_cli as _fixtures

checking = _fixtures.checking
local_setup = _fixtures.local_setup
terminal = _fixtures.terminal


@pytest.fixture(autouse=True)
def real_input_pty(tmp_path, monkeypatch):
    if not sys.stdin.isatty():
        pytest.skip('BLOCKED: stdin is not a real terminal; run via exec_command tty:true and pytest -s')
    # This autouse fence runs before local_setup constructs the app/inventory.
    # Keep even a passive provider-home suggestion inside this fixture.
    home = tmp_path / 'os-home'
    home.mkdir()
    for name in ('HOME', 'USERPROFILE'):
        monkeypatch.setenv(name, str(home))
    for name, directory in [('CODEX_HOME', home / '.codex'), ('CLAUDE_CONFIG_DIR', home / '.claude')]:
        directory.mkdir()
        monkeypatch.setenv(name, str(directory))


@pytest.fixture
def pty_cli(terminal, local_setup, tmp_path, monkeypatch):
    from okto_nexus.adapters.inbound.cli import connect, main, work
    from okto_nexus.adapters.outbound import git_project_hint
    t = terminal
    home = tmp_path / 'pty-home'
    provider = tmp_path / 'own-provider-home'
    provider.mkdir()
    actions = []
    service = SimpleNamespace(adapter=SimpleNamespace(home=home, host='127.0.0.1', port=8202),
        inspect=lambda: actions.append('inspect') or {'state': 'ready'},
        ensure_running=lambda **_: actions.append('ensure') or {'state': 'ready'})
    monkeypatch.setattr(connect, 'resolve_local_service', lambda _: service)
    monkeypatch.setattr(connect, 'LocalOperatorHTTP', lambda **_: t.call)
    monkeypatch.chdir(t.selection['project'])

    def forbidden(*_a, **_kw):
        pytest.fail('Explicit PTY demo must not enter chat or discover an executable')

    monkeypatch.setattr(work, 'interactive_work', forbidden)
    monkeypatch.setattr(git_project_hint, '_trusted_git', forbidden)

    def run(tokens):
        assert sys.stdin.isatty(), 'real input terminal was lost'
        return main.main([*tokens, '--home', str(home), '--provider-home', str(provider)])

    return SimpleNamespace(t=t, home=home, actions=actions, run=run, client=local_setup[2])


def test_real_terminal_measurement():
    print('PTY_MEASUREMENT ' + json.dumps(dict(stdin_tty=sys.stdin.isatty(),
        stdout_tty=sys.stdout.isatty(), stderr_tty=sys.stderr.isatty(), platform=sys.platform)), flush=True)
    assert sys.stdin.isatty()


def test_json_with_real_tty_never_requests_input(pty_cli):
    c = pty_cli
    product = StringIO()
    print('PTY_JSON_BEGIN_NO_INPUT_EXPECTED', flush=True)
    with redirect_stdout(product):
        code = c.run(['connect', 'codxe', 'PTY Demo', '--profile', 'json', '--plan', '--json'])
    text = product.getvalue()
    result = json.loads(text)
    assert code == 3 and result['code'] == 'CLIENT_SELECTION_REQUIRED'
    assert '\x1b' not in text
    assert c.t.turns == c.t.probes == []
    assert c.actions == ['inspect']
    print('PTY_JSON_COMPLETED_WITHOUT_INPUT', flush=True)


def test_cancel_from_actual_terminal_does_not_check_or_test(pty_cli):
    c = pty_cli
    print('PTY_CANCEL_BEGIN: send cancel at the review prompt', flush=True)
    assert c.run(['connect', 'codex', 'PTY Demo', '--profile', 'cancelled', '--no-chat']) == 0
    assert c.t.turns == c.t.probes == []
    saved = json.loads((c.home / 'terminal/profiles/cancelled.json').read_text(encoding='utf-8'))
    assert saved['state'] == 'review'
    print('PTY_CANCEL_CONFIRMED_ZERO_TESTS', flush=True)


def test_confirm_and_resume_use_actual_terminal_without_replaying_test(pty_cli):
    from test_connection_setup_recovery import snapshot
    c = pty_cli
    print('PTY_CONFIRM_BEGIN: send y at the review prompt', flush=True)
    assert c.run(['connect', 'codex', 'PTY Demo', '--profile', 'confirmed', '--no-chat']) == 0
    assert len(c.t.turns) == len(c.t.probes) == 1
    before = snapshot(c.t.deps)
    print('PTY_RESUME_BEGIN: send y at canonical resume confirmation', flush=True)
    assert c.run(['connect', '--profile', 'confirmed', '--no-chat']) == 0
    assert snapshot(c.t.deps) == before
    assert len(c.t.turns) == len(c.t.probes) == 1
    print('PTY_RESUME_CONFIRMED_ONE_TEST_TOTAL', flush=True)


def test_ctrl_c_after_issued_test_preserves_checkpoint_and_only_ends_observation(pty_cli, monkeypatch):
    from test_connection_setup_recovery import snapshot
    c = pty_cli
    active = SimpleNamespace(gate=None)

    async def pending(entry, request, candidate):
        c.t.turns.append(request['client_intent_id'])
        entry.update(status='running', stage='Own synthetic test waiting')
        active.gate = asyncio.Event()
        print('PTY_TEST_ISSUED_SEND_CTRL_C_NOW', flush=True)
        await active.gate.wait()
        entry.update(status='succeeded', stage='Synthetic test stopped normally')

    monkeypatch.setattr(c.t.app.state.connection_tests, 'run', pending)
    print('PTY_INTERRUPT_BEGIN: send y; wait for issued marker before Ctrl-C', flush=True)
    code = c.run(['connect', 'codex', 'PTY Interrupt', '--profile', 'interrupted', '--no-chat'])
    assert code == 130
    path = c.home / 'terminal/profiles/interrupted.json'
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['state'] == 'test_submitted'
    assert len(c.t.turns) == len(c.t.probes) == 1
    assert not snapshot(c.t.deps)['execution_bindings']
    assert not snapshot(c.t.deps)['runtime_execution_grants']
    assert active.gate is not None
    # Observation ended; this explicit fixture-only signal releases its inert
    # peer before TestClient lifespan closes. No cancellation sent by CLI.
    c.client.portal.call(active.gate.set)
    print('PTY_INTERRUPT_CHECKPOINT_PRESERVED_NO_BINDING_OR_GRANT', flush=True)
    # This peer did not own a process, real model or external service.
