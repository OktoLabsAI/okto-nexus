"""Finite Sonnet campaign context; no inherited Codex controller or effect on import."""
from pathlib import Path
import hashlib
import json
import os
import sys

HERE = Path(__file__).resolve().parent

class Refused(RuntimeError):
    pass

def require(value, reason):
    if not value:
        raise Refused(reason)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(65536), b''):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def pin(value):
    require(sha(value['path']) == value['sha256'], 'PIN_CHANGED')
    return Path(value['path'])

def reserve(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())

def public_save(context, name, value):
    require(Path(name).name == name and name.endswith('.json'), 'PUBLIC_NAME_INVALID')
    reserve(context.PUBLIC / name, dict(value, phase1_plan_sha256=context.plan_sha256))

def require_tags(value, context):
    require(value.get('phase1_plan_sha256') == context.plan_sha256, 'RECEIPT_PLAN_CHANGED')

class Context:
    def __init__(self, path, expected_sha256):
        self.plan_path = Path(path).resolve()
        require(self.plan_path == HERE / 'phase1-plan.json', 'OWN_PLAN_REQUIRED')
        require(sha(self.plan_path) == expected_sha256, 'PLAN_CHANGED')
        self.plan_sha256 = expected_sha256
        self.P = read_json(self.plan_path)
        require(self.P['scope'] == 'OWN_NEXUS_LIFECYCLE_OPERATOR_ONLY_NO_PROVIDER', 'PHASE1_SCOPE_CHANGED')
        require(self.P['provider_calls'] == 0 and self.P['force_authorized'] is False, 'PHASE1_EFFECT_SCOPE_CHANGED')
        self.ROOT = Path(self.P['campaign_root'])
        self.CONTROL = HERE
        self.PUBLIC, self.PRIVATE = HERE / 'public', HERE / 'private'
        self.C = self.P['commands']
        self.installed = read_json(pin(self.P['installation']))
        require(Path(sys.prefix).resolve() == Path(self.installed['python_prefix']).resolve(), 'INSTALLED_PREFIX_REQUIRED')
        require(set(self.P['runtime_pins']) == {'request_context.py','phase1.py','reused_observation.py','operator_bootstrap.py'}, 'FINITE_RUNTIME_PINS_REQUIRED')
        for name, source in self.P['runtime_pins'].items():
            require(Path(source['path']).resolve() == HERE/name, 'SOURCE_OUTSIDE_CANDIDATE')
            pin(source)
        require(self.P['topology']['origin'] == 'http://127.0.0.1:58631', 'OWN_ORIGIN_REQUIRED')
        for key in ('server_home', 'operator_home', 'connector_state', 'connector_project'):
            require(Path(self.P['paths'][key]).resolve().is_relative_to(self.ROOT.resolve()), 'OWN_PATH_REQUIRED')

    def env(self):
        names = {'SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','APPDATA','LOCALAPPDATA','USERPROFILE','USERNAME','USERDOMAIN'}
        value = {k:v for k,v in os.environ.items() if k.upper() in names}
        value['PATH'] = os.pathsep.join(self.C['required_parent_path'])
        value['PYTHONUTF8'] = '1'
        return value

    def require_ready(self):
        from phase1 import current_ready
        return current_ready(self)

    def common_args(self):
        return ['--plan', str(self.plan_path), '--expected-plan-sha256', self.plan_sha256]

    def normal_stop(self):
        from phase1 import lifecycle
        return lifecycle(self, 'stop')

    def handoff(self, reason, **details):
        return {'status':'ROOT_RECONCILIATION_REQUIRED','reason':reason,**details}
