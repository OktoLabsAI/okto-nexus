"""Configuration and approval gate for these finite campaign scripts only."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import os
import sys

class Refused(RuntimeError): pass

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require(condition, code):
    if not condition: raise Refused(code)

def pinned_json(pin):
    require(sha(pin['path'])==pin['sha256'],'ADOPTION_SOURCE_CHANGED')
    return json.loads(Path(pin['path']).read_bytes())

def verify_adoption(proposal):
    adoption=proposal['adoption']
    previous=pinned_json(adoption['predecessor_proposal_pin'])
    closure=pinned_json(adoption['predecessor_closure_pin'])
    checkpoint=adoption['predecessor_checkpoint_pin']
    reconciled=pinned_json(checkpoint)
    original=adoption['predecessor_original_checkpoint_pin']
    require(sha(original['path'])==original['sha256'],'ORIGINAL_PREDECESSOR_CHECKPOINT_CHANGED')
    companion=pinned_json(adoption['predecessor_companion_pin'])
    installation_proposal=pinned_json(adoption['installation_proposal_pin'])
    installation_closure=pinned_json(adoption['installation_closure_pin'])
    final=pinned_json(adoption['predecessor_final_presence_pin'])
    installed=pinned_json(adoption['installation_result_pin'])
    reservation=adoption['installation_reservation_pin']
    require(sha(reservation['path'])==reservation['sha256'],'INSTALLATION_RESERVATION_CHANGED')
    require(previous['revision']==13 and closure['campaign_revision']==13
        and closure['format']=='okto.m1.closed_campaign'
        and closure['status']=='CLOSED_NORMAL_CLEANUP_ACCEPTANCE_NOT_INFERRED'
        and closure['closed_without_force'] is True and closure['all_temporary_tasks_absent'] is True
        and closure['data_retained'] is True
        and closure['controller_mutated'] is False and closure['replay_allowed'] is False
        and closure['controller_checkpoint_sha256']==original['sha256']
        and closure['final_presence_sha256']==adoption['predecessor_final_presence_pin']['sha256']
        and closure['cumulative_reserved_admissions']==9
        and closure['cumulative_minimum_observed_tokens']==134199
        and closure['proposal_sha256']==adoption['predecessor_proposal_pin']['sha256'],
        'CLOSED_PREDECESSOR_ADOPTION_REQUIRED')
    require(companion['status']=='CLOSED_RECONCILED_SETTLED_ACCEPTANCE_NOT_INFERRED'
        and companion['campaign_revision']==13 and companion['reconciled_unsettled_requests']==0
        and companion['cumulative_reserved_admissions']==9
        and companion['cumulative_minimum_observed_tokens']==134199
        and companion['files']['original_closure']==adoption['predecessor_closure_pin']
        and companion['files']['original_checkpoint']==original
        and companion['files']['derived_checkpoint']==checkpoint
        and companion['original_closure_and_checkpoint_unchanged'] is True
        and companion['force_used'] is False and companion['late_native_decision_posts']==0
        and all(r['settled'] for r in reconciled['requests'].values())
        and reconciled['faults']==['DEADLINE120','WORK_TERMINAL_FAILED'],
        'RECONCILED_PREDECESSOR_REQUIRED')
    require(installed['format']=='okto.base06.installation' and installed['revision']==1
        and installed['status']=='INSTALLED_VERIFIED' and installed['proposal_revision']==12
        and installation_proposal['revision']==12
        and installed['proposal_sha256']==adoption['installation_proposal_pin']['sha256']
        and installed['approval_sha256']==installation_closure['approval_sha256']
        and installed['campaign_root']==installation_proposal['paths']['campaign_root']
        and installed['python']==proposal['package_pins']['python']
        and installed['python_prefix']==proposal['package_pins']['python_prefix']
        and installed['payload_count']==983 and installed['pip_check']['returncode']==0
        and installed['reservation_sha256']==reservation['sha256'],
        'ADOPTED_V12_INSTALLATION_REQUIRED')
    require(proposal['controller_preparation']['ancestry']['closure_sha256']==adoption['predecessor_closure_pin']['sha256']
        and proposal['controller_preparation']['ancestry']['checkpoint_sha256']==checkpoint['sha256']
        and proposal['controller_preparation']['ancestry']['closure_companion_sha256']==adoption['predecessor_companion_pin']['sha256'],
        'ADOPTION_ANCESTRY_CHANGED')
    return {'predecessor_closed':True,'installation_adopted':True,'payload_count':983}

def load():
    parser=argparse.ArgumentParser()
    parser.add_argument('--proposal',required=True)
    parser.add_argument('--expected-proposal-sha256',required=True)
    parser.add_argument('--approval-path')
    parser.add_argument('--approval-sha256')
    args, remaining=parser.parse_known_args()
    try:
        raw=Path(args.proposal).read_bytes()
        require(hashlib.sha256(raw).hexdigest()==args.expected_proposal_sha256,'PROPOSAL_HASH_MISMATCH')
        proposal=json.loads(raw)
        require(proposal.get('revision')==14,'PROPOSAL_REVISION_MISMATCH')
        # Before package imports, checkpoint creation, binding, HTTP, or Popen.
        require(args.approval_path and args.approval_sha256,'AUTHORIZATION_REQUIRED')
        receipt_raw=Path(args.approval_path).read_bytes()
        require(hashlib.sha256(receipt_raw).hexdigest()==args.approval_sha256,'APPROVAL_HASH_MISMATCH')
        receipt=json.loads(receipt_raw)
        root=Path(proposal['paths']['campaign_root']).resolve()
        control=Path(proposal['paths']['control_root']).resolve()
        require(control==root/'successor14' and control!=root,'CONTROL_ROOT_MISMATCH')
        contract=proposal['controller_preparation']
        require(receipt.get('status')=='USER_APPROVED' and receipt.get('proposal_revision')==14
          and receipt.get('proposal_sha256')==args.expected_proposal_sha256
          and receipt.get('campaign_root')==str(root)
          and receipt.get('control_root')==str(control)
          and receipt.get('policy')==contract['policy'] and receipt.get('ancestry')==contract['ancestry']
          and isinstance(receipt.get('user_quote'),str) and bool(receipt['user_quote'].strip()),'APPROVAL_SCOPE_MISMATCH')
        pin_status=proposal['package_pins'].get('status')
        require(pin_status=='QUALIFIED_ADOPTED_V12_INSTALLATION','ADOPTED_PACKAGE_PINS_REQUIRED')
        verify_adoption(proposal)
        require(proposal['execution_bundle'].get('status')=='FROZEN_QUALIFIED','EXECUTION_BUNDLE_REQUIRED')
        bundle=proposal['execution_bundle']
        for entry in bundle['files'].values():
            require(sha(entry['path'])==entry['sha256'],'EXECUTION_MODULE_CHANGED')
        require(Path(sys.prefix).resolve()==Path(proposal['package_pins']['python_prefix']).resolve(),'INSTALLED_PREFIX_MISMATCH')
        for entry in proposal['package_pins']['files']:
            require(sha(entry['path'])==entry['sha256'],'PRODUCT_PIN_CHANGED')
        require(sha(proposal['paths']['codex_executable'])==proposal['native_selection']['fingerprint'].split(':',1)[1],'NATIVE_PIN_CHANGED')
        commands_entry=bundle['commands']
        require(sha(commands_entry['path'])==commands_entry['sha256'],'COMMANDS_CHANGED')
        commands=json.loads(Path(commands_entry['path']).read_text())
        require(len(commands['steps'])==8,'LIFECYCLE_ALLOCATION_INVALID')
        require(all('--force' not in s['argv'] for s in commands['steps']),'FORCE_EXCLUDED')
        require(all(s['argv'][0]==proposal['package_pins']['python'] for s in commands['steps']),'LIFECYCLE_INTERPRETER_MISMATCH')
        for key,value in proposal['paths'].items():
            if key!='codex_executable':require(Path(value).resolve().is_relative_to(root),'PATH_OUTSIDE_FRESH_ROOT')
        modules=Path(contract['public_directory'])
        for name,key in [('controller.py','controller_sha256'),('token_collector.py','collector_sha256')]:
            require(sha(modules/name)==contract[key],'CONTROLLER_CHANGED')
        values={}
        for node in ast.parse((modules/'controller.py').read_text()).body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('POLICY','ANCESTRY'):
                values[node.targets[0].id]=ast.literal_eval(node.value)
        require(values=={'POLICY':contract['policy'],'ANCESTRY':contract['ancestry']},'CONTROLLER_CONTRACT_CHANGED')
        require(Path(proposal['paths']['public_evidence']).resolve()==control/'public'
            and Path(proposal['paths']['private_evidence']).resolve()==control/'private','CONTROL_EVIDENCE_ROOT_MISMATCH')
        return Context(args,remaining,proposal,commands,root,modules)
    except (OSError,ValueError,KeyError,Refused) as error:
        print(json.dumps({'status':'REFUSED_BEFORE_DISPATCH','code':str(error) if isinstance(error,Refused) else type(error).__name__}),flush=True)
        raise SystemExit(2) from None

class Context:
    def __init__(self,args,remaining,proposal,commands,root,modules):
        self.args,self.remaining,self.P,self.C,self.ROOT,self.modules=args,remaining,proposal,commands,root,modules
        self.CONTROL=Path(proposal['paths']['control_root']).resolve()
        self.PUBLIC,self.PRIVATE=self.CONTROL/'public',self.CONTROL/'private'
    def common_args(self):
        return ['--proposal',self.args.proposal,'--expected-proposal-sha256',self.args.expected_proposal_sha256,
                '--approval-path',self.args.approval_path,'--approval-sha256',self.args.approval_sha256]
    def env(self):
        allowed={'SYSTEMROOT','WINDIR','COMSPEC','TEMP','TMP','USERPROFILE','LOCALAPPDATA','APPDATA','HOMEDRIVE','HOMEPATH','USERNAME','USERDOMAIN','PATHEXT','PROGRAMDATA','PROGRAMFILES','PROGRAMFILES(X86)'}
        value={k:v for k,v in os.environ.items() if k.upper() in allowed}
        value['PATH']=os.pathsep.join(self.C['required_parent_path'])
        value['PYTHONIOENCODING']='utf-8'
        return value
    def controller(self,*,create=False):
        sys.path.insert(0,str(self.modules))
        from controller import Controller
        return Controller(self.PRIVATE/'controller.json',self.ROOT,create=create,
            approval_path=self.args.approval_path,approval_sha256=self.args.approval_sha256,
            expected_proposal_sha256=self.args.expected_proposal_sha256)
    def lifecycle_script(self): return Path(__file__).with_name('m1_v14_lifecycle.py')
    def stop_argv(self,component):
        return [self.P['package_pins']['python'],'-I','-B',str(self.lifecycle_script()),*self.common_args(),component,'stop']

def reserve_json(path,document):
    """Exclusive durable action reservation; never replace or replay an existing one."""
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(document,stream,indent=2);stream.flush();os.fsync(stream.fileno())
