"""Prepared S1 browser driver: explicit toolchain and path-only Windows env.

Application/peer env is NOT provided here: the unchanged Owned.start supplies
its separate total-ownTemp environment with empty provider executable PATH.
"""
import hashlib
import os
from pathlib import Path

import psutil

HOST_KEYS=(
    'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE','OS','PROCESSOR_ARCHITECTURE',
    'PROGRAMFILES','PROGRAMFILES(X86)','COMMONPROGRAMFILES','COMMONPROGRAMFILES(X86)',
    'PROGRAMDATA','USERPROFILE','HOME','HOMEDRIVE','HOMEPATH','LOCALAPPDATA','APPDATA',
)


def environment(root):
    root=Path(root).resolve()
    assert root.name.startswith('nexus-hst-browser-')
    # Read ONLY these path/system keys, never the provider/CLI-auth namespace.
    env={key:os.environ[key] for key in HOST_KEYS if key in os.environ}
    (root/'tmp').mkdir(exist_ok=True)
    (root/'cwd/.playwright').mkdir(parents=True,exist_ok=True)
    (root/'cli-global/.playwright').mkdir(parents=True,exist_ok=True)
    (root/'cli-daemon').mkdir(exist_ok=True)
    env.update(PATH='',TEMP=str(root/'tmp'),TMP=str(root/'tmp'),
        PWTEST_DAEMON_SESSION_DIR=str(root/'cli-daemon'),
        PWTEST_CLI_GLOBAL_CONFIG=str(root/'cli-global'),
        NO_UPDATE_NOTIFIER='1',DEBUG='pw:browser*,pw:api',
        PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    assert set(env)==set(key for key in HOST_KEYS if key in os.environ)|{
        'PATH','TEMP','TMP','PWTEST_DAEMON_SESSION_DIR','PWTEST_CLI_GLOBAL_CONFIG',
        'NO_UPDATE_NOTIFIER','DEBUG','PYTHONUTF8','PYTHONDONTWRITEBYTECODE'}
    return env


def capture(root, known, tooling):
    """Read only already-owned births; require one exact own profile main."""
    root=Path(root).resolve()
    profile=(root/'browser-profile').resolve()
    records=[]
    for item in known.values():
        if Path(item['exe']).resolve()!=Path(tooling['chrome']).resolve():
            continue
        try:
            process=psutil.Process(item['pid'])
            if abs(process.create_time()-item['birth'])>=.01 or process.exe()!=item['exe']:
                continue
            argv=process.cmdline()
        except psutil.NoSuchProcess:
            continue
        if any(arg.startswith('--type=') for arg in argv):
            continue
        directories=[arg.split('=',1)[1] for arg in argv if arg.startswith('--user-data-dir=')]
        assert len(directories)==1
        assert Path(directories[0]).resolve()==profile and profile.is_relative_to(root)
        assert '--remote-debugging-pipe' in argv and '--headless' in argv
        assert '--no-sandbox' not in argv
        assert '--disable-blink-features=AutomationControlled' in argv
        records.append(dict(pid=item['pid'],birth=item['birth'],exe=item['exe'],argv=argv,
            own_profile=str(profile),before_home_navigation=True))
    assert len(records)==1,'No exact live own main Chrome proof; never navigate/fallback'
    assert hashlib.sha256(Path(tooling['chrome']).read_bytes()).hexdigest()==tooling['chrome_sha256']
    return {'status':'EXACT_OWN_PROFILE_MAIN_CAPTURED','records':records,
            'environment_policy':'windows-path-allowlist-app-env-own-v1',
            'host_keys':list(HOST_KEYS),'environment_equivalence_to_working_capture_claimed':False,
            'no_personal_cli_config':'Own PWTEST_CLI_GLOBAL_CONFIG; own cwd .playwright; no npx/npm/update check',
            'app_environment':'Unchanged Owned.start total-ownTemp/own credentials/provider PATH empty'}
