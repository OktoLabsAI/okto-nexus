"""Private configuration evidence for the reviewed Windows Claude resume path."""

import hashlib
import os
import re
from pathlib import Path

from nexus_connector_core.environment import ProcessHTTPEnvironment
from nexus_connector_core.native.saved_history_file import file_version, plain_path
from nexus_connector_core.protocol import canonical_json, strict_json

_LIMIT = 2 * 1024 * 1024
_STATE_FILES = ('settings.json', 'CLAUDE.md')
_WORKSPACE_FILES = ('settings.json', 'settings.local.json', 'CLAUDE.md', 'CLAUDE.local.md')
_SETTINGS_KEYS = frozenset({
    '$schema', 'permissions', 'env', 'hooks', 'model', 'effortLevel', 'useAutoModeDuringPlan',
})


def capture_claude_resume_profile(prepared, environment):
    settings = prepared.intent.harness_settings
    home = environment.get('CLAUDE_CONFIG_DIR')
    if (prepared.intent.adapter_id != 'claude_stream' or settings.permission_mode != 'plan'
            or settings.inherit_global_mcps == 'enabled' or prepared.intent.mcp_preset
            or (isinstance(environment, ProcessHTTPEnvironment)
                and (environment.preset_entries or len(environment.http_templates) > 1
                     or any(template.always_allow_tools or template.allow_remote_http
                            for template in environment.http_templates)))
            or type(home) is not str or not Path(home).is_absolute()):
        return None
    if not any(environment.get(key) for key in ('ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN')):
        return None
    return observe_claude_resume_profile(home, prepared.cwd)


def observe_claude_resume_profile(state_home, workspace):
    """Fingerprint the local settings sources recognized by the reviewed route."""
    home, project = Path(state_home), Path(workspace)
    if (not home.is_absolute() or not project.is_absolute()
            or '..' in home.parts or '..' in project.parts):
        return None
    try:
        if _has_external_policy():
            return None
        for path in (*home.parents, home, *project.parents, project):
            plain_path(path, directory=True)
        for relative in ('agents', 'commands', 'skills', 'rules', 'plugins/installed_plugins.json',
                         '.credentials.json', 'remote-settings.json', 'managed-settings.json'):
            if _present(home / relative):
                return None
        for relative in ('.mcp.json', '.claude/agents', '.claude/commands', '.claude/skills', '.claude/rules'):
            if _present(project / relative):
                return None
        if _has_parent_instructions(project):
            return None
        sources = {
            **{'user/' + name: home / name for name in _STATE_FILES},
            **{'project/' + name: project / '.claude' / name for name in _WORKSPACE_FILES},
            'project/CLAUDE.md-root': project / 'CLAUDE.md',
            'project/CLAUDE.local.md-root': project / 'CLAUDE.local.md',
        }
        rules = []
        fingerprints = {}
        for key, path in sources.items():
            data = _read(path)
            fingerprints[key] = hashlib.sha256(data).hexdigest() if data is not None else None
            if data is None:
                continue
            if path.suffix == '.md':
                # Imported instructions have their own closure and need review.
                if re.search(rb'(^|\s)@\S', data):
                    return None
                continue
            rule = _review_settings(data)
            if rule is None:
                return None
            rules.append(rule)
        if not any(rules):
            return None
        return {'state_home': str(home),
                'settings_sha256': hashlib.sha256(canonical_json(fingerprints)).hexdigest()}
    except (OSError, ValueError, TypeError, RecursionError):
        return None


def _review_settings(data):
    document = strict_json(data.decode('utf-8'))
    if type(document) is not dict or set(document) - _SETTINGS_KEYS:
        return None
    permissions = document.get('permissions', {})
    hooks = document.get('hooks', {})
    env = document.get('env', {})
    if (type(permissions) is not dict or set(permissions) - {'deny'}
            or type(permissions.get('deny', [])) is not list
            or any(type(rule) is not str for rule in permissions.get('deny', []))
            or document.get('useAutoModeDuringPlan', False) is not False
            or type(hooks) is not dict or set(hooks) - {'Stop', 'StopFailure'}
            or type(env) is not dict or any(name not in {
                'ANTHROPIC_BASE_URL', 'ANTHROPIC_MODEL', 'DISABLE_AUTOUPDATER', 'NO_PROXY',
                'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC',
            } for name in env)):
        return None
    return '*' in permissions.get('deny', [])


def _has_external_policy():
    if os.name != 'nt':
        return True
    import winreg

    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, r'SOFTWARE\Policies\ClaudeCode', 0, winreg.KEY_READ | view):
                    return True
            except FileNotFoundError:
                continue
    locations = {location for name in ('ProgramW6432', 'ProgramFiles') if (location := os.environ.get(name))}
    return not locations or any(_present(Path(location) / 'ClaudeCode') for location in locations)


def _has_parent_instructions(project):
    return any(_present(parent / name) for parent in project.parents
               for name in ('CLAUDE.md', 'CLAUDE.local.md', '.claude'))


def _present(path):
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    return True


def _read(path):
    if not _present(path):
        return None
    plain_path(path.parent, directory=True)
    original = file_version(plain_path(path, directory=False))
    if original[2] > _LIMIT:
        raise ValueError('Unbounded Claude configuration.')
    with path.open('rb') as stream:
        opened = file_version(os.fstat(stream.fileno()))
        if opened[:4] != original[:4]:
            raise ValueError('Claude configuration changed.')
        data = stream.read(_LIMIT + 1)
        if len(data) != original[2] or file_version(os.fstat(stream.fileno())) != opened:
            raise ValueError('Claude configuration changed.')
    if file_version(plain_path(path, directory=False)) != original:
        raise ValueError('Claude configuration changed.')
    return data
