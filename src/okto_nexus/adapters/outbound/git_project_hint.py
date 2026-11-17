"""Bounded, local-only naming hints, never workspace or execution authority.

At most six read-only Git invocations share a two-second deadline. Each response
(stdout AND stderr combined) is capped at 64 KiB: maximum retained output for
the whole discovery is 384 KiB. No URL, config value or diagnostic crosses the
adapter boundary. Callers must keep an approved/saved name instead of discovering
again during recovery; this function has no checkpoint or authorization access.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Literal
import unicodedata
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class GitProjectHint:
    name: str | None
    source: Literal['git_origin', 'git_worktree', 'directory']
    status: str
    reason: str


class _ReadFailure(Exception):
    """Only fixed public reason codes, never subprocess text."""


def _safe_name(value: str) -> str | None:
    if (not value or len(value) > 160 or value != value.strip() or value in {'.', '..'}
            or any(c in '/\\:' or unicodedata.category(c).startswith('C')
                   or unicodedata.category(c).startswith('Z') and c != ' ' for c in value)):
        return None
    return value


def _git_environment(environment: dict[str, str]) -> dict[str, str]:
    # Git's namespace includes config injection pairs, object alternates, traces,
    # external diff/SSH commands and repository overrides. Strip ALL variants;
    # environment is case insensitive on Windows. Never mutate the parent.
    cleaned = {k: v for k, v in environment.items() if not k.upper().startswith('GIT_')}
    cleaned.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM=os.devnull,
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0',
                   GIT_OPTIONAL_LOCKS='0', GIT_PAGER='cat', GIT_ATTR_NOSYSTEM='1',
                   GIT_CONFIG_COUNT='0', LC_ALL='C')
    return cleaned


def _trusted_git(root: Path, *, deadline: float | None = None) -> Path | None:
    """Use only absolute PATH entries outside the project; never shell/PATHEXT.

    PATH is the host installation allowlist, not a search of project files or
    the disk. Reject relative/empty entries, UNC binaries and symlinks resolving
    into the project (or the invocation directory). No executable is probed.
    """
    excluded = [root]
    try:
        excluded.append(Path.cwd().resolve(strict=True))
    except OSError:
        pass
    # The execution root may be a monorepo subdirectory. A sibling tools/git
    # inside its repository is still project-controlled, even with absolute PATH.
    # Only inspect ancestor metadata (including .git files in worktrees); never
    # run a candidate to establish that trust boundary or scan directories.
    for base in tuple(dict.fromkeys(excluded)):
        for depth, ancestor in enumerate((base, *base.parents)):
            if depth >= 64 or deadline is not None and time.monotonic() >= deadline:
                return None
            try:
                (ancestor / '.git').lstat()
            except (FileNotFoundError, NotADirectoryError):
                continue
            except OSError:
                return None  # An unreadable trust boundary is not approval.
            excluded.append(ancestor)
    for index, entry in enumerate(os.environ.get('PATH', '').split(os.pathsep, 64)):
        if index >= 64 or deadline is not None and time.monotonic() >= deadline:
            break
        directory = Path(entry)
        if not entry or not directory.is_absolute() or entry.startswith(('\\\\', '//')):
            continue
        try:
            candidate = (directory / ('git.exe' if os.name == 'nt' else 'git')).resolve(strict=True)
            if (not candidate.is_file() or not os.access(candidate, os.X_OK)
                    or any(candidate.is_relative_to(base) for base in excluded)
                    or str(candidate).startswith(('\\\\', '//'))):
                continue
            return candidate
        except (OSError, ValueError, RuntimeError):
            continue
    return None


def _read_available(pipe) -> bytes | None:
    """Read without waiting for EOF, including when a descendant owns the pipe.

    None means not ready; b'' means EOF. Windows 3.11 cannot set an anonymous
    pipe nonblocking through os.set_blocking, so peek its available byte count.
    No reader thread/blocked join survives discovery.
    """
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        peek = kernel.PeekNamedPipe
        peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                         wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        peek.restype = wintypes.BOOL
        available = wintypes.DWORD()
        if not peek(msvcrt.get_osfhandle(pipe.fileno()), None, 0, None,
                    ctypes.byref(available), None):
            if ctypes.get_last_error() in {109, 232}:  # broken/disconnected pipe
                return b''
            raise OSError('Git observation pipe unavailable')
        if not available.value:
            return None
        return os.read(pipe.fileno(), min(4096, available.value))
    os.set_blocking(pipe.fileno(), False)
    try:
        return os.read(pipe.fileno(), 4096)
    except BlockingIOError:
        return None


class _GitReader:
    def __init__(self, executable: Path, root: Path, *, deadline: float | None = None):
        self.executable, self.root = executable, root
        self.deadline = time.monotonic() + 2.0 if deadline is None else deadline
        self.calls = self.total_bytes = 0
        self.active: subprocess.Popen | None = None

    def run(self, args: list[str]) -> tuple[int, bytes, bytes]:
        if self.calls >= 6:
            raise _ReadFailure('git_call_limit')
        # Reserve a small part of the same deadline for kill/wait/close.
        observation_deadline = self.deadline - 0.15
        if time.monotonic() >= observation_deadline:
            raise _ReadFailure('git_timeout')
        self.calls += 1
        output = [bytearray(), bytearray()]
        size = 0
        try:
            self.active = subprocess.Popen(
                [str(self.executable), *args], cwd=str(self.root),
                env=_git_environment(dict(os.environ)), shell=False,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            ended = set()
            while True:
                remaining = observation_deadline - time.monotonic()
                if remaining <= 0:
                    raise _ReadFailure('git_timeout')
                progressed = False
                for index, pipe in enumerate((self.active.stdout, self.active.stderr)):
                    if index in ended:
                        continue
                    chunk = _read_available(pipe)
                    if chunk == b'':
                        ended.add(index)
                    elif chunk is not None:
                        progressed = True
                        room = max(0, 65536 - size)
                        kept = chunk[:room]
                        output[index].extend(kept)
                        size += len(kept)
                        if len(chunk) > room:
                            raise _ReadFailure('git_output_limit')
                code = self.active.poll()
                if code is not None and len(ended) == 2:
                    return code, bytes(output[0]), bytes(output[1])
                if not progressed:
                    time.sleep(min(remaining, 0.005))
        except OSError:
            raise _ReadFailure('git_unavailable') from None
        finally:
            if self.active is not None:
                if self.active.poll() is None:
                    try:
                        self.active.kill()
                    except OSError:
                        pass  # it may have exited between poll and kill; wait proves it
                try:
                    self.active.wait(timeout=max(0.001, self.deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    raise _ReadFailure('git_cleanup_unconfirmed') from None
                finally:
                    self.active.stdout.close()
                    self.active.stderr.close()
                self.active = None  # only after the owned process is reaped
            self.total_bytes += size


def _origin_name(origin: str) -> str | None:
    if (origin != origin.strip() or any(unicodedata.category(c).startswith('C')
            or unicodedata.category(c).startswith('Z') and c != ' ' for c in origin)
            or re.search(r'%2f|%5c', origin, re.IGNORECASE)):
        return None
    # Windows drives must be recognized before SCP's host:path spelling.
    if re.match(r'^[A-Za-z]:[\\/]', origin):
        path = origin.replace('\\', '/')
    elif '://' in origin:
        try:
            parsed = urlsplit(origin)
            if parsed.scheme != 'file' and (not parsed.hostname or parsed.port is not None
                                              and not 0 < parsed.port < 65536):
                return None
        except ValueError:
            return None
        if parsed.scheme not in {'https', 'http', 'ssh', 'file'}:
            return None
        if parsed.scheme != 'file' and not parsed.netloc:
            return None
        path = parsed.path
    elif re.match(r'^(?:[^/@:]+@)?[^/:]+:.+', origin):
        path = origin.split(':', 1)[1]
        if path.startswith(':'):  # e.g. ext:: invokes a transport helper.
            return None
    else:
        path = origin.replace('\\', '/')
    parts = [p for p in path.split('/') if p]
    if not parts:
        return None
    try:
        name = unquote(parts[-1], encoding='utf-8', errors='strict')
    except (UnicodeError, ValueError):
        return None
    if name.endswith('.git'):
        name = name[:-4]
    return _safe_name(name)


def discover_project_name(root: Path, *, plan: bool = False) -> GitProjectHint:
    """Suggest a label for an existing physical directory, without side effects.

    ``plan`` intentionally does not resolve Git or run ANY subprocess. Discovery
    only examines the nearest repository of ``root``; a repo label never changes
    that execution directory, identifies a workspace or overrides saved intent.
    """
    deadline = time.monotonic() + 2.0
    try:
        physical = Path(root).resolve(strict=True)
        if not physical.is_dir():
            raise ValueError()
    except (OSError, ValueError, RuntimeError):
        return GitProjectHint(None, 'directory', 'unconfirmed', 'invalid_project_name')

    def fallback(reason, worktree=None):
        name = _safe_name((worktree or physical).name)
        return GitProjectHint(name, 'git_worktree' if worktree else 'directory',
                              'fallback' if name else 'unconfirmed', reason)

    if plan:
        return GitProjectHint(_safe_name(physical.name), 'directory', 'not_run_plan', 'not_run_plan')
    executable = _trusted_git(physical, deadline=deadline)
    if executable is None:
        return fallback('git_timeout' if time.monotonic() >= deadline else 'git_unavailable')
    reader = _GitReader(executable, physical, deadline=deadline)
    worktree = None
    prefix = ['--no-pager', '-C', str(physical)]
    try:
        code, output, error = reader.run(prefix + ['rev-parse', '--show-toplevel'])
        if code:
            reason = ('dubious_ownership' if b'dubious ownership' in error or b'safe.directory' in error
                      else 'not_a_repository')
            return fallback(reason)
        try:
            text = output.decode('utf-8', errors='strict').removesuffix('\n').removesuffix('\r')
            if '\n' in text or '\r' in text:
                raise ValueError()
            candidate = Path(text)
            if not candidate.is_absolute():
                raise ValueError()
            candidate = candidate.resolve(strict=True)
            if not candidate.is_dir() or not physical.is_relative_to(candidate):
                raise ValueError()
            worktree = candidate
        except (UnicodeError, ValueError, OSError, RuntimeError):
            return fallback('git_config_unavailable')

        def config(scope, key, *, boolean=False):
            command = ['config', scope, '--no-includes']
            command += ['--bool', '--get'] if boolean else ['--null', '--get-all']
            code, output, _ = reader.run(prefix + command + [key])
            if code not in {0, 1}:
                raise _ReadFailure('git_config_unavailable')
            if code == 1:
                return []
            text = output.decode('utf-8', errors='strict')
            return [text.strip()] if boolean else text.removesuffix('\0').split('\0')

        origins = config('--local', 'remote.origin.url')
        if config('--local', 'extensions.worktreeConfig', boolean=True) == ['true']:
            origins += config('--worktree', 'remote.origin.url')
        unique = set(origins)
        if not unique:
            return fallback('origin_missing', worktree)
        if len(unique) != 1:
            return fallback('origin_ambiguous', worktree)
        name = _origin_name(unique.pop())
        if name is None:
            return fallback('origin_invalid', worktree)
        return GitProjectHint(name, 'git_origin', 'discovered', 'git_origin')
    except UnicodeError:
        return fallback('git_config_unavailable', worktree)
    except _ReadFailure as error:
        reason = str(error)
        if reason in {'git_call_limit', 'git_cleanup_unconfirmed'}:
            reason = 'git_config_unavailable'
        return fallback(reason, worktree)
