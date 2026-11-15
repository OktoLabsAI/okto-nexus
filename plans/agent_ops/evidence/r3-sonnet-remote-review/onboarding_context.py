"""Independent no-model draft/review stage; phase1 remains immutable."""
from pathlib import Path
import argparse
import json
import os
import sys

from request_context import Context as Phase1, require, read_json, pin, sha, reserve

HERE=Path(__file__).resolve().parent

class Context:
    def __init__(self,path,expected):
        path=Path(path).resolve()
        require(path==HERE/'onboarding-plan.json' and sha(path)==expected,'ONBOARDING_PLAN_CHANGED')
        self.amendment_sha256=expected;self.P=read_json(path)
        require(self.P['scope']=='SONNET_CANONICAL_DRAFT_AND_OPERATOR_REVIEW_ONLY'
            and self.P['provider_calls']==0 and self.P['selected_actions']==['draft','plan'],'ONBOARDING_SCOPE_CHANGED')
        base=pin(self.P['phase1_plan'])
        self.base=Phase1(base,self.P['phase1_plan']['sha256'])
        self.ROOT,self.PUBLIC,self.PRIVATE=self.base.ROOT,self.base.PUBLIC,self.base.PRIVATE
        self.python=self.base.P['package_pins']['python']
        require(set(self.P['runtime_pins'])=={'onboarding_context.py','onboarding_entry.py','remote_onboarding.py'},'RUNTIME_SCOPE_CHANGED')
        for name,value in self.P['runtime_pins'].items():
            require(Path(value['path']).resolve()==HERE/name,'RUNTIME_PATH_CHANGED');pin(value)
        pin(self.P['native'])
        require(self.P['model']=='sonnet' and self.P['permission_mode']=='default'
            and self.P['global_mcps']=='disabled','HARNESS_SELECTION_CHANGED')
        require(self.P['origin']==self.base.P['topology']['origin']
            and self.P['server_id']==self.base.P['expected_server_id']
            and self.P['operator_profile']=='m1-sonnet-human','OWN_SERVER_OR_OPERATOR_REQUIRED')
        for key in ('connector_state','operator_home'):
            require(self.P['paths'][key]==self.base.P['paths'][key],'OWN_HOME_CHANGED')
        require(self.P['paths']['project']==self.base.P['paths']['connector_project'],'OWN_PROJECT_CHANGED')
        require(self.P['setup_request_id']=='m1-sonnet-remote-setup-01'
            and self.P['profile']==self.P['agent_id']=='m1-sonnet-remote','NEW_SONNET_NAMESPACE_REQUIRED')
        self.profile_path=Path(self.P['paths']['operator_home'])/'terminal/profiles'/(self.P['profile']+'.json')

    def require_ready(self):
        owner=self.base.require_ready()
        account=read_json(self.PUBLIC/'operator-bootstrap-result.json')
        require(account.get('phase1_plan_sha256')==self.base.plan_sha256
            and account.get('status')=='OPERATOR_AUTHENTICATED'
            and account.get('profile')==self.P['operator_profile']
            and account.get('server_id')==self.P['server_id']
            and account.get('origin')==self.P['origin'],'OPERATOR_BOOTSTRAP_UNCONFIRMED')
        return owner

    def connector_env(self):
        value=self.base.env()
        value['PATH']=os.pathsep.join(self.P['connector_parent_path'])
        return value

    def save(self,name,value):
        require(Path(name).name==name and name.startswith('sonnet-') and name.endswith('.json'),'PUBLIC_NAME_INVALID')
        reserve(self.PUBLIC/name,dict(value,amendment_sha256=self.amendment_sha256))

    def require_connector_ready(self):
        raise RuntimeError('TRANSFER_NOT_SELECTED_BY_THIS_NO_MODEL_STAGE')


def load():
    p=argparse.ArgumentParser()
    p.add_argument('--plan',required=True);p.add_argument('--expected-plan-sha256',required=True)
    p.add_argument('action',choices=('draft','plan'))
    a=p.parse_args();return Context(a.plan,a.expected_plan_sha256),a.action
