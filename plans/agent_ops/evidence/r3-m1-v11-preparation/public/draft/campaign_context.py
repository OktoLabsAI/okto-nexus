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
        require(proposal.get('revision')==11,'PROPOSAL_REVISION_MISMATCH')
        # Before package imports, checkpoint creation, binding, HTTP, or Popen.
        require(args.approval_path and args.approval_sha256,'AUTHORIZATION_REQUIRED')
        receipt_raw=Path(args.approval_path).read_bytes()
        require(hashlib.sha256(receipt_raw).hexdigest()==args.approval_sha256,'APPROVAL_HASH_MISMATCH')
        receipt=json.loads(receipt_raw)
        root=Path(proposal['paths']['campaign_root']).resolve()
        contract=proposal['controller_preparation']
        require(receipt.get('status')=='USER_APPROVED' and receipt.get('proposal_revision')==11
          and receipt.get('proposal_sha256')==args.expected_proposal_sha256
          and receipt.get('campaign_root')==str(root)
          and receipt.get('policy')==contract['policy'] and receipt.get('ancestry')==contract['ancestry']
          and isinstance(receipt.get('user_quote'),str) and bool(receipt['user_quote'].strip()),'APPROVAL_SCOPE_MISMATCH')
        pin_status=proposal['package_pins'].get('status')
        require(pin_status in ('QUALIFIED_FINAL','QUALIFIED_ARTIFACTS_INSTALL_REQUIRED'),'FINAL_PACKAGE_PINS_REQUIRED')
        if pin_status=='QUALIFIED_ARTIFACTS_INSTALL_REQUIRED':
            installation=proposal['base06_installation']
            installed=json.loads(Path(installation['result']).read_text())
            require(installed.get('format')=='okto.base06.installation' and installed.get('revision')==1
                and installed.get('status')=='INSTALLED_VERIFIED' and installed.get('proposal_revision')==11
                and installed.get('proposal_sha256')==args.expected_proposal_sha256
                and installed.get('approval_sha256')==args.approval_sha256
                and installed.get('campaign_root')==str(root)
                and installed.get('python')==installation['python']
                and installed.get('python_prefix')==installation['python_prefix']
                and installed.get('payload_count')==installation['expected_payload_count'] and installed.get('pip_check',{}).get('returncode')==0
                and installed.get('reservation_sha256')==sha(installation['reservation']),
                'TIMED_INSTALLATION_PROOF_REQUIRED')
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
        return Context(args,remaining,proposal,commands,root,modules)
    except (OSError,ValueError,KeyError,Refused) as error:
        print(json.dumps({'status':'REFUSED_BEFORE_DISPATCH','code':str(error) if isinstance(error,Refused) else type(error).__name__}),flush=True)
        raise SystemExit(2) from None

class Context:
    def __init__(self,args,remaining,proposal,commands,root,modules):
        self.args,self.remaining,self.P,self.C,self.ROOT,self.modules=args,remaining,proposal,commands,root,modules
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
        return Controller(self.ROOT/'private/controller.json',self.ROOT,create=create,
            approval_path=self.args.approval_path,approval_sha256=self.args.approval_sha256,
            expected_proposal_sha256=self.args.expected_proposal_sha256)
    def lifecycle_script(self): return Path(__file__).with_name('m1_v11_lifecycle.py')
    def stop_argv(self,component):
        return [self.P['package_pins']['python'],'-I','-B',str(self.lifecycle_script()),*self.common_args(),component,'stop']

def reserve_json(path,document):
    """Exclusive durable action reservation; never replace or replay an existing one."""
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(document,stream,indent=2);stream.flush();os.fsync(stream.fileno())
