"""Keep Connector CLI observations aligned with its pinned service environment."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recovery_context import require, sha
root = Path(__file__).resolve().parent
require(sha(root/'recovery_binding.py') == '4dfe7f41b3f627daa8aaf2f6b27eca03d8af92f6d0512af94e59c0b02b8daea0', 'BINDING_SOURCE_CHANGED')
require(sha(root/'recovery_probe_once.py') == '7c63ec42bee41d3507fb54e227f2a961abbfcf08bb0db566fa95eeea48aeada7', 'ENVIRONMENT_SOURCE_CHANGED')
import recovery_binding as binding
from recovery_probe_once import service_environment

class EnvironmentView:
    def __init__(self, base):
        self.base = base
        self.environment = service_environment(base)
    def __getattr__(self, name):
        return getattr(self.base, name)
    def connector_env(self):
        return dict(self.environment)

invoke = binding.Context.invoke
def invoke_aligned(self, action, argv, *, connector=False):
    base = self.base
    try:
        if connector:
            self.base = EnvironmentView(base)
        return invoke(self, action, argv, connector=connector)
    finally:
        self.base = base

binding.Context.invoke = invoke_aligned
binding.main()
