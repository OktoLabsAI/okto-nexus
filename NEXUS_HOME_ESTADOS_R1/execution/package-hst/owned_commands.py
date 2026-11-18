"""Finite child commands with closed stdin and ownership-fenced containment.

Controller dependency psutil belongs to the host, never the frozen test prefix.
"""
import os
from pathlib import Path
import signal
import subprocess
import time

import psutil


def identity(process):
    return dict(pid=process.pid, birth=process.create_time(), exe=process.exe())


def matching(info):
    try:
        process = psutil.Process(info['pid'])
        if process.create_time() == info['birth'] and process.exe() == info['exe']:
            return process
    except psutil.NoSuchProcess:
        pass
    return None


def run_owned(argv, *, root, cwd, env, log, timeout, allow_canonical=True):
    root = Path(root).resolve()
    known = {}
    canonical = {}
    actions = []
    started = time.monotonic()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env,
        stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
        creationflags=flags, start_new_session=os.name != 'nt')
    process.stdin.close()
    parent = psutil.Process(process.pid)
    owner = identity(parent)
    known[owner['pid']] = owner
    timed_out = False
    break_at = None
    normal_exit_at = None
    killed = False
    while True:
        for info in list(known.values()):
            current = matching(info)
            if current is None:
                continue
            try:
                children = current.children(recursive=True)
                for child in children:
                    known.setdefault(child.pid, identity(child))
                if allow_canonical and current.pid not in canonical:
                    command = current.cmdline()
                    module = 'okto_nexus.adapters.inbound.mcp.server'
                    if module in command and 'serve' in command and '--home' in command and '--port' in command:
                        home = Path(command[command.index('--home')+1]).resolve()
                        port = command[command.index('--port')+1]
                        if home.is_relative_to(root) and port.isdecimal():
                            canonical[current.pid] = dict(info=info, home=str(home), port=port)
            except psutil.NoSuchProcess:
                pass
        alive = [info for info in known.values() if matching(info) is not None]
        code = process.poll()
        now = time.monotonic()
        if code is not None and not alive:
            break
        if code is not None and normal_exit_at is None:
            normal_exit_at = now
        expired = now-started >= timeout or (normal_exit_at is not None and now-normal_exit_at >= 10)
        if expired and break_at is None:
            timed_out = True
            # Prefer the application's own stop for a proven own foreground Server.
            for server in canonical.values():
                if matching(server['info']) is None:
                    continue
                stop = ['rtk', 'proxy', server['info']['exe'], '-I', '-B', '-m',
                    'okto_nexus.adapters.inbound.mcp.server', 'service', 'stop',
                    '--home', server['home'], '--host', '127.0.0.1',
                    '--port', server['port'], '--timeout', '15', '--json']
                receipt = run_owned(stop, root=root, cwd=cwd, env=env, log=log,
                    timeout=30, allow_canonical=False)
                actions.append(dict(kind='canonical_own_service_stop', result=receipt))
            if matching(owner) is not None:
                process.send_signal(signal.CTRL_BREAK_EVENT if os.name == 'nt' else signal.SIGINT)
                actions.append(dict(kind='owned_group_interrupt', **owner))
            break_at = time.monotonic()
        if break_at is not None and time.monotonic()-break_at >= 30:
            for info in reversed(list(known.values())):
                current = matching(info)
                if current is not None:
                    current.kill()
                    actions.append(dict(kind='owned_timeout_kill', **info))
                    killed = True
            break
        time.sleep(.1)
    try:
        exit_code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        exit_code = None
    until = time.monotonic()+5
    while time.monotonic() < until and any(matching(info) is not None for info in known.values()):
        time.sleep(.1)
    remaining = [info for info in known.values() if matching(info) is not None]
    listeners = []
    for info in remaining:
        current = matching(info)
        if current:
            try:
                listeners.extend(dict(pid=current.pid, address=list(c.laddr))
                    for c in current.net_connections(kind='inet') if c.status == psutil.CONN_LISTEN)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                listeners.append(dict(pid=current.pid, inspection='unavailable'))
    return dict(exit_code=exit_code, timed_out=timed_out, force_used=killed,
        stdin='closed PIPE', known_processes=list(known.values()), actions=actions,
        remaining_known_processes=remaining, remaining_listeners=listeners,
        success=exit_code == 0 and not timed_out and not killed and not remaining,
        observation_limit='100ms ancestry polling cannot enumerate every short-lived child; no such completeness claim')
