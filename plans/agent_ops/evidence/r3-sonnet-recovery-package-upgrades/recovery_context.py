"""New recovery namespace; no service, credential or provider effects on import."""
from pathlib import Path
import hashlib
import json
import os
import sys

HERE = Path(__file__).resolve().parent


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def pin(value):
    require(sha(value['path']) == value['sha256'], 'PIN_CHANGED')
    return Path(value['path'])


def reserve(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.writing')
    require(not path.exists(), 'SELECTION_ALREADY_RESERVED')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    # Windows rename refuses an existing destination; no receipt overwrites.
    temporary.rename(path)


def public_save(context, name, value):
    require(Path(name).name == name and name.endswith('.json'), 'PUBLIC_NAME_INVALID')
    reserve(context.PUBLIC / name, dict(value, lifecycle_plan_sha256=context.plan_sha256))


def require_tags(value, context):
    require(value.get('lifecycle_plan_sha256') == context.plan_sha256, 'RECEIPT_PLAN_CHANGED')


class RecoveryContext:
    def __init__(self, path, expected_sha256):
        self.plan_path = Path(path).resolve()
        require(self.plan_path == HERE / 'lifecycle-plan.json', 'OWN_PLAN_REQUIRED')
        require(sha(self.plan_path) == expected_sha256, 'PLAN_CHANGED')
        self.plan_sha256 = expected_sha256
        self.P = read_json(self.plan_path)
        require(self.P['scope'] == 'OWN_RECOVERY_LIFECYCLE_NO_CREDENTIAL_OR_PROVIDER', 'LIFECYCLE_SCOPE_CHANGED')
        require(self.P['provider_calls'] == 0 and self.P['force_authorized'] is False, 'EFFECT_SCOPE_CHANGED')
        self.ROOT = Path(self.P['campaign_root'])
        self.CONTROL = HERE
        self.PUBLIC, self.PRIVATE = HERE / 'public', HERE / 'private'
        self.C = self.P['commands']
        self.installed = read_json(pin(self.P['installation']))
        self.python = self.P['python']
        require(Path(sys.prefix).resolve() == Path(self.installed['python_prefix']).resolve(), 'INSTALLED_PREFIX_REQUIRED')
        require(Path(sys.executable).absolute() == Path(self.python).absolute(), 'INSTALLED_PYTHON_REQUIRED')
        for name, source in self.P['runtime_pins'].items():
            require(Path(source['path']).resolve() == HERE / name, 'SOURCE_OUTSIDE_CANDIDATE')
            pin(source)
        require(self.P['topology']['origin'] == 'http://127.0.0.1:58631', 'OWN_ORIGIN_REQUIRED')
        for name in ('server_home', 'connector_state', 'operator_home', 'connector_project'):
            require(Path(self.P['paths'][name]).resolve().is_relative_to(self.ROOT.resolve()), 'OWN_PATH_REQUIRED')

    def save(self, name, value):
        public_save(self, name, value)

    def require_tags(self, value):
        require_tags(value, self)

    def env(self):
        names = {'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'APPDATA',
                 'LOCALAPPDATA', 'USERPROFILE', 'USERNAME', 'USERDOMAIN'}
        result = {k: v for k, v in os.environ.items() if k.upper() in names}
        result['PATH'] = os.pathsep.join(self.C['required_parent_path'])
        result['PYTHONUTF8'] = '1'
        return result

    def connector_env(self):
        # Backend choice does not grant file-storage consent; executor gates that separately.
        return dict(self.env(), OKTO_NEXUS_CONNECTOR_VAULT='file')

    def require_nexus_ready(self):
        from recovery_observation import current_ready
        return current_ready(self)

    def require_ready(self):
        from recovery_connector import current_ready
        return {'nexus': self.require_nexus_ready(), 'connector': current_ready(self)}

    def require_migrated(self, component):
        result = read_json(self.PUBLIC / (component + '-upgrade-apply-returned.json'))
        self.require_tags(result)
        require(result['returncode'] == 0 and result['projection'].get('applied') is True,
                'CANONICAL_UPGRADE_REQUIRED')
        require(sha(self.P['source_contexts'][component]['path']) == result['target_context_sha256'],
                'MIGRATED_CONTEXT_CHANGED')

    def common_args(self):
        return ['--plan', str(self.plan_path), '--expected-plan-sha256', self.plan_sha256]


Context = RecoveryContext
