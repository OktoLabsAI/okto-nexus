"""Own Connector lifecycle and exact reviewed remote transfer; no paid work selector."""
from pathlib import Path
import argparse
import os

from request_context import Context as Phase1,require,read_json,pin,sha,reserve

HERE=Path(__file__).resolve().parent

class TransferContext:
    def __init__(self,path,expected):
        path=Path(path).resolve()
        require(path==HERE/'transfer-plan.json' and sha(path)==expected,'TRANSFER_PLAN_CHANGED')
        self.amendment_sha256=expected;self.P=read_json(path)
        require(self.P['scope']=='OWN_CONNECTOR_LIFECYCLE_AND_EXACT_REMOTE_TRANSFER_NO_WORK'
            and self.P['provider_turns_selected']==0,'TRANSFER_SCOPE_CHANGED')
        basepin=self.P['phase1_plan'];self.base=Phase1(pin(basepin),basepin['sha256'])
        self.ROOT,self.PUBLIC,self.PRIVATE=self.base.ROOT,self.base.PUBLIC,self.base.PRIVATE
        self.C,self.installed=self.base.C,self.base.installed
        self.python=self.base.P['package_pins']['python']
        require(set(self.P['runtime_pins'])=={'transfer_context.py','transfer_entry.py','connector_lifecycle.py','remote_onboarding.py'},'FINITE_TRANSFER_RUNTIME_REQUIRED')
        for name,value in self.P['runtime_pins'].items():
            require(Path(value['path']).resolve()==HERE/name,'TRANSFER_SOURCE_OUTSIDE_CANDIDATE');pin(value)
        for value in self.P['protected_dependencies'].values():pin(value)
        pin(self.P['protected_transfer']);pin(self.P['native']);pin(self.P['canonical_review'])
        require(self.P['origin']==self.base.P['topology']['origin'] and self.P['server_id']==self.base.P['expected_server_id'],
            'SERVER_IDENTITY_CHANGED')
        require(self.P['operator_profile']=='m1-sonnet-human' and self.P['profile']==self.P['agent_id']=='m1-sonnet-remote'
            and self.P['setup_request_id']=='m1-sonnet-remote-setup-01','SONNET_IDENTITY_CHANGED')
        for key in ('server_home','operator_home','connector_state'):
            require(self.P['paths'][key]==self.base.P['paths'][key],'OWN_HOME_CHANGED')
        self.profile_path=Path(self.P['paths']['operator_home'])/'terminal/profiles'/(self.P['profile']+'.json')

    def require_ready(self):return self.base.require_ready()

    def connector_env(self):
        value=self.base.env();value['PATH']=os.pathsep.join(self.P['connector_parent_path'])
        return value

    def save(self,name,value):
        require(Path(name).name==name and name.startswith(('sonnet-','connector-')) and name.endswith('.json'),'PUBLIC_NAME_INVALID')
        reserve(self.PUBLIC/name,dict(value,amendment_sha256=self.amendment_sha256))

    def require_tags(self,value):
        require(value.get('amendment_sha256')==self.amendment_sha256,'TRANSFER_RECEIPT_CHANGED')

    def require_connector_ready(self):
        from connector_lifecycle import current_ready
        return current_ready(self)


def load():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('action',choices=('install','start','select','watch','transfer','stop','cleanup','uninstall'))
    a=p.parse_args();return TransferContext(a.plan,a.expected_plan_sha256),a.action
