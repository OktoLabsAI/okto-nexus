"""Actual installed CLI diagnostics cannot create an absent instance."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_doctor_absent_instance_is_passive_without_provider_or_server_checks(tmp_path):
    home = tmp_path / 'absent-home'
    own_profile = tmp_path / 'own-profile'
    empty_path = tmp_path / 'empty-path'
    own_profile.mkdir()
    empty_path.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(('OKTO_', 'NEXUS_', 'OPENAI_', 'ANTHROPIC_', 'CODEX_', 'CLAUDE_'))
           and key.upper() not in {'PYTHONPATH', 'PYTHONHOME'}}
    env.update({key: str(own_profile) for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA')})
    env.update(PATH=str(empty_path), PYTHONUTF8='1', OKTO_NEXUS_NO_BANNER='1')
    command = [sys.executable, '-I', '-m', 'okto_nexus.adapters.inbound.cli.main',
               'doctor', '--home', str(home), '--project', str(tmp_path), '--profile', 'absent', '--json']
    result = subprocess.run(command, cwd=tmp_path, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == 3, result.stderr or result.stdout
    report = json.loads(result.stdout)
    checks = {item['id']: item for item in report['checks']}
    assert checks['project_profile']['code'] == 'PROFILE_ABSENT'
    assert checks['local_service']['evidence']['state'] == 'stopped'
    assert checks['provider_login']['code'] == 'PROVIDER_LOGIN_NOT_CHECKED'
    assert checks['managed_session']['code'] == 'SESSION_NOT_CHECKED'
    assert checks['work_result']['code'] == 'WORK_NOT_CHECKED'
    assert all(value is False for value in report['effects'].values())
    assert not home.exists()
    assert list(own_profile.iterdir()) == []
    assert list(empty_path.iterdir()) == []
    assert Path(command[0]).resolve() == Path(sys.executable).resolve()
