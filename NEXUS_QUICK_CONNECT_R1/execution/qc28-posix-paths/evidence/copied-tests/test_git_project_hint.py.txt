"""Local-only Git suggestions; repository fixtures never use accounts or a remote."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

from okto_nexus.adapters.outbound import git_project_hint as hints
from okto_nexus.domain.quick_connect import NameDiscovery


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / 'copy'
    root.mkdir()
    executable = shutil.which('git')
    if not executable:
        pytest.skip('Git is not installed; missing-Git behavior is separately covered')
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull,
               GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
               HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path))
    empty = tmp_path / 'empty-template'
    empty.mkdir()

    def git(*args, cwd=root):
        return subprocess.run([executable, '-c', 'init.templateDir=' + str(empty),
                               '-c', 'core.hooksPath=' + str(empty), '-C', str(cwd), *args],
                              env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              check=True, timeout=5).stdout

    git('init', '--quiet')
    return root, git


@pytest.mark.parametrize('origin', [
    'https://example.invalid/org/project.git', 'git@example.invalid:org/project.git',
    'ssh://git@example.invalid:2222/org/project.git', 'file:///srv/git/project.git',
    '/srv/git/project.git', r'C:\repos\project.git', 'relative/project.git',
    'https://user:PRIVATE@example.invalid/org/project.git?token=PRIVATE#PRIVATE',
])
def test_origin_formats_are_local_text_and_never_disclose_url(repo, origin):
    root, git = repo
    git('config', '--local', 'remote.origin.url', origin)
    result = hints.discover_project_name(root)
    assert (result.name, result.source, result.status) == ('project', 'git_origin', 'discovered')
    assert NameDiscovery(status=result.status, reason=result.reason).status == 'discovered'
    public = json.dumps(asdict(result))
    assert 'PRIVATE' not in public and 'example.invalid' not in public and origin not in public


def test_subdirectory_keeps_physical_root_and_nearest_repository(repo):
    root, git = repo
    git('config', 'remote.origin.url', 'https://example.invalid/monorepo.git')
    sub = root / 'apps' / 'api'
    sub.mkdir(parents=True)
    assert hints.discover_project_name(sub).name == 'monorepo'
    assert sub.is_dir() and not (sub / '.git').exists()
    git('init', '--quiet', cwd=sub)
    assert hints.discover_project_name(sub).name == 'api'


def test_no_origin_uses_worktree_not_upstream(repo):
    root, git = repo
    git('config', 'remote.upstream.url', 'https://example.invalid/wrong.git')
    result = hints.discover_project_name(root)
    assert (result.name, result.source, result.reason) == ('copy', 'git_worktree', 'origin_missing')


def test_distinct_origins_ambiguous_even_with_same_basename(repo):
    root, git = repo
    for url in ['https://one.invalid/project.git', 'https://two.invalid/project.git']:
        git('config', '--add', 'remote.origin.url', url)
    result = hints.discover_project_name(root)
    assert (result.name, result.source, result.reason) == ('copy', 'git_worktree', 'origin_ambiguous')


def test_exact_duplicate_origins_are_not_ambiguous(repo):
    root, git = repo
    for _ in range(2):
        git('config', '--add', 'remote.origin.url', 'https://example.invalid/project.git')
    assert hints.discover_project_name(root).name == 'project'


@pytest.mark.parametrize('origin', [
    'https://host.invalid/bad%2fname.git', 'https://host.invalid/bad%5cname.git',
    'https://host.invalid/bad%0aname.git', 'https://host.invalid/bad\x1bname.git',
    'https://host.invalid/bad\u200bname.git', 'https://host.invalid/.git',
    'https://host.invalid/bad\u00a0name.git', 'https://:123/project.git',
    'ext::evil command', 'https://host.invalid/' + 'x' * 161,
])
def test_invalid_origin_falls_back_without_echo(repo, origin):
    root, git = repo
    git('config', 'remote.origin.url', origin)
    result = hints.discover_project_name(root)
    assert result.name == 'copy' and result.source == 'git_worktree'
    assert result.reason == 'origin_invalid'
    assert origin not in json.dumps(asdict(result))


def test_local_includes_and_global_config_are_not_origin_sources(repo, tmp_path, monkeypatch):
    root, git = repo
    include = tmp_path / 'secret-config'
    include.write_text('[remote "origin"]\n url = https://secret.invalid/wrong.git\n')
    git('config', 'include.path', str(include))
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', str(include))
    monkeypatch.setenv('GIT_CONFIG_SYSTEM', str(include))
    result = hints.discover_project_name(root)
    assert result.name == 'copy' and result.reason == 'origin_missing'


def test_gitfile_and_worktree_only_origin(repo, tmp_path):
    root, git = repo
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '--allow-empty', '--quiet', '-m', 'fixture')
    linked = tmp_path / 'linked'
    git('worktree', 'add', '--quiet', '--detach', str(linked))
    git('config', '--local', 'extensions.worktreeConfig', 'true')
    git('config', '--worktree', 'remote.origin.url', 'https://example.invalid/linked-origin.git', cwd=linked)
    assert (linked / '.git').is_file()
    assert hints.discover_project_name(linked).name == 'linked-origin'
    git('config', '--local', 'remote.origin.url', 'https://example.invalid/common.git')
    assert hints.discover_project_name(linked).reason == 'origin_ambiguous'


def test_case_insensitive_git_environment_overrides_do_not_redirect(repo, tmp_path, monkeypatch):
    root, git = repo
    git('config', 'remote.origin.url', 'https://example.invalid/right.git')
    for key, value in {'GIT_DIR': str(tmp_path), 'GIT_WORK_TREE': str(tmp_path),
                       'GIT_COMMON_DIR': str(tmp_path), 'GIT_CONFIG_COUNT': '1',
                       'GIT_CONFIG_KEY_0': 'remote.origin.url',
                       'GIT_CONFIG_VALUE_0': 'https://secret.invalid/wrong.git',
                       'GIT_CONFIG': str(tmp_path / 'not-a-config')}.items():
        monkeypatch.setenv(key, value)
    before = dict(os.environ)
    assert hints.discover_project_name(root).name == 'right'
    assert dict(os.environ) == before
    cleaned = hints._git_environment({'gIt_DiR': 'private', 'GIT_CONFIG_PARAMETERS': 'private'})
    assert all('private' != value for value in cleaned.values())


def test_plan_and_invalid_directory_never_resolve_or_spawn_git(tmp_path, monkeypatch):
    monkeypatch.setattr(hints, '_trusted_git', lambda *_a, **_k: pytest.fail('plan discovered executable'))
    monkeypatch.setattr(subprocess, 'Popen', lambda *_a, **_k: pytest.fail('plan spawned'))
    assert hints.discover_project_name(tmp_path, plan=True).reason == 'not_run_plan'
    assert hints.discover_project_name(tmp_path / 'missing').reason == 'invalid_project_name'


def test_no_git_and_non_repository_are_explicit(tmp_path, monkeypatch):
    real = hints._trusted_git(tmp_path)
    monkeypatch.setattr(hints, '_trusted_git', lambda *_a, **_k: None)
    assert hints.discover_project_name(tmp_path).reason == 'git_unavailable'
    if real:
        monkeypatch.setattr(hints, '_trusted_git', lambda *_a, **_k: real)
        assert hints.discover_project_name(tmp_path).reason == 'not_a_repository'


def test_path_search_rejects_project_relative_and_symlink_candidates(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    binary = root / ('git.exe' if os.name == 'nt' else 'git')
    binary.write_bytes(b'not executable')
    binary.chmod(0o755)
    monkeypatch.setenv('PATH', os.pathsep.join(['', '.', str(root), 'relative']))
    assert hints._trusted_git(root) is None


def test_path_search_does_not_follow_external_symlink_into_project(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    install = tmp_path / 'install'
    install.mkdir()
    name = 'git.exe' if os.name == 'nt' else 'git'
    target = root / name
    target.write_bytes(b'not executable')
    target.chmod(0o755)
    try:
        (install / name).symlink_to(target)
    except OSError:
        pytest.skip('Creating symlinks is not permitted on this host')
    monkeypatch.setenv('PATH', str(install))
    assert hints._trusted_git(root) is None


def test_path_search_has_entry_and_time_budgets(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    install = tmp_path / 'install'
    install.mkdir()
    name = 'git.exe' if os.name == 'nt' else 'git'
    binary = install / name
    binary.write_bytes(b'never executed')
    binary.chmod(0o755)
    entries = [str(tmp_path / f'absent-{i}') for i in range(64)]
    monkeypatch.setenv('PATH', os.pathsep.join([*entries, str(install)]))
    assert hints._trusted_git(root) is None
    monkeypatch.setenv('PATH', str(install))
    assert hints._trusted_git(root) == binary
    assert hints._trusted_git(root, deadline=time.monotonic() - 1) is None


def test_non_repository_and_malformed_config_never_leak_diagnostics(repo, tmp_path):
    root, _ = repo
    (root / '.git' / 'config').write_text('[bad PRIVATE\n')
    result = hints.discover_project_name(root)
    assert result.source == 'directory' and result.status == 'fallback'
    assert 'PRIVATE' not in json.dumps(asdict(result))


def test_directory_without_usable_name_does_not_invent_one(monkeypatch):
    monkeypatch.setattr(hints, '_trusted_git', lambda *_a, **_k: None)
    result = hints.discover_project_name(Path(Path.cwd().anchor), plan=True)
    assert result.name is None and result.status == 'not_run_plan'


def test_safe_utf8_and_terminal_git_suffix_only_are_preserved(repo):
    root, git = repo
    git('config', 'remote.origin.url', 'https://example.invalid/Aplicação.git.backup.git')
    before = Path.cwd()
    result = hints.discover_project_name(root)
    assert result.name == 'Aplicação.git.backup'
    assert Path.cwd() == before


def test_discovery_deadline_includes_executable_resolution(tmp_path, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(hints.time, 'monotonic', lambda: clock[0])

    def slow_resolver(_, **_kwargs):
        clock[0] = 3.0
        return Path(sys.executable)

    monkeypatch.setattr(hints, '_trusted_git', slow_resolver)
    monkeypatch.setattr(subprocess, 'Popen', lambda *_a, **_kw: pytest.fail('deadline exceeded'))
    result = hints.discover_project_name(tmp_path)
    assert result.reason == 'git_timeout'
    NameDiscovery(status=result.status, reason=result.reason)


def test_failed_ownership_is_not_overridden_or_echoed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(hints, '_trusted_git', lambda *_a, **_k: Path(sys.executable))

    def run(self, args):
        calls.append(args)
        return 128, b'', b'fatal: detected dubious ownership; PRIVATE safe.directory'

    monkeypatch.setattr(hints._GitReader, 'run', run)
    result = hints.discover_project_name(tmp_path)
    assert result.reason == 'dubious_ownership'
    assert len(calls) == 1 and all('safe.directory' not in word for word in calls[0])
    assert 'PRIVATE' not in json.dumps(asdict(result))


def test_spawn_contract_is_bounded_read_only_and_cleans_environment(repo, monkeypatch):
    root, _ = repo
    original = subprocess.Popen
    calls = []

    def capture(argv, **kw):
        calls.append((argv, kw))
        return original(argv, **kw)

    monkeypatch.setattr(subprocess, 'Popen', capture)
    hints.discover_project_name(root)
    assert 1 <= len(calls) <= 6
    for argv, kw in calls:
        assert Path(argv[0]).is_absolute() and kw['shell'] is False
        assert kw['stdin'] == subprocess.DEVNULL and kw['cwd'] == str(root)
        assert kw['env']['GIT_CONFIG_GLOBAL'] == os.devnull
        assert kw['env']['GIT_TERMINAL_PROMPT'] == '0'
        assert 'rev-parse' in argv or 'config' in argv
        if 'config' in argv:
            assert '--no-includes' in argv and ('--get' in argv or '--get-all' in argv)


def test_deadline_and_call_limit_reap_owned_children(tmp_path):
    reader = hints._GitReader(Path(sys.executable), tmp_path)
    start = time.monotonic()
    with pytest.raises(hints._ReadFailure, match='git_timeout'):
        reader.run(['-c', 'import time;time.sleep(20)'])
    assert time.monotonic() - start < 3.5
    assert reader.active is None
    reader = hints._GitReader(Path(sys.executable), tmp_path)
    reader.calls = 6
    with pytest.raises(hints._ReadFailure, match='git_call_limit'):
        reader.run(['-c', 'pass'])


def test_deadline_is_shared_and_does_not_restart_between_calls(tmp_path):
    reader = hints._GitReader(Path(sys.executable), tmp_path)
    assert reader.run(['-c', 'pass'])[0] == 0
    deadline = reader.deadline
    reader.deadline = time.monotonic() - 1
    with pytest.raises(hints._ReadFailure, match='git_timeout'):
        reader.run(['-c', 'pass'])
    assert reader.calls == 1 and reader.active is None and deadline > reader.deadline


def _process_running(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        stat = Path(f'/proc/{pid}/stat')
        return not stat.exists() or stat.read_text().split(') ', 1)[1][0] != 'Z'
    except ProcessLookupError:
        return False


def test_parent_exit_with_inherited_pipe_does_not_block_or_kill_descendant(tmp_path):
    stop = tmp_path / 'child.stop'
    pid_file = tmp_path / 'child.pid'
    child = ('import os,time;from pathlib import Path;'
             f'Path({str(pid_file)!r}).write_text(str(os.getpid()));'
             f'stop=Path({str(stop)!r});'
             'exec("while not stop.exists():\\n time.sleep(0.01)")')
    parent = f'import subprocess,sys;subprocess.Popen([sys.executable,"-c",{child!r}])'
    reader = hints._GitReader(Path(sys.executable), tmp_path)
    start = time.monotonic()
    pid = None
    try:
        with pytest.raises(hints._ReadFailure, match='git_timeout'):
            reader.run(['-c', parent])
        assert time.monotonic() - start < 3
        assert reader.active is None  # parent reaped, no blocking reader thread
        pid = int(pid_file.read_text())
        assert _process_running(pid)  # the adapter did not kill another process
    finally:
        stop.touch()  # normal stop of this test's own descendant, never a third party
        if pid is None and pid_file.exists():
            pid = int(pid_file.read_text())
        until = time.monotonic() + 3
        while pid is not None and _process_running(pid) and time.monotonic() < until:
            time.sleep(0.02)
        assert pid is not None and not _process_running(pid)


@pytest.mark.parametrize('stream', ['stdout', 'stderr', 'combined'])
def test_output_limit_is_combined_and_reaps_owned_child(tmp_path, stream):
    reader = hints._GitReader(Path(sys.executable), tmp_path)
    code = (f'import sys;sys.{stream}.buffer.write(b"x"*2000000)' if stream != 'combined'
            else 'import sys;sys.stdout.buffer.write(b"x"*40000);sys.stdout.flush();'
                 'sys.stderr.buffer.write(b"x"*40000)')
    with pytest.raises(hints._ReadFailure, match='git_output_limit'):
        reader.run(['-c', code])
    assert reader.active is None
    assert reader.total_bytes <= 6 * 65536


def test_metadata_hint_is_not_an_identity_or_root_selector(repo):
    root, git = repo
    git('config', 'remote.origin.url', 'https://example.invalid/first.git')
    first = hints.discover_project_name(root)
    git('config', 'remote.origin.url', 'https://example.invalid/second.git')
    second = hints.discover_project_name(root)
    assert first.name == 'first' and second.name == 'second'
    assert set(asdict(first)) == {'name', 'source', 'status', 'reason'}
    with pytest.raises(AttributeError):
        first.name = 'changed'
