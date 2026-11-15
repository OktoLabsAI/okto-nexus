from copy import deepcopy
from pathlib import Path
import sys
import subprocess
import pytest
from remote_onboarding import validate_draft,validate_inventory,draft_commands
from request_context import Refused

P={'setup_request_id':'m1-sonnet-remote-setup-01','origin':'http://127.0.0.1:58631','profile':'m1-sonnet-remote'}
def draft():
    return {'format':'okto.remote-setup-draft','version':1,'setup_run_id':P['setup_request_id'],
        'server_origin':P['origin'],'installation':{'adapter_id':'claude_stream','candidate_ref':'opaque-from-inventory'},
        'start_at_login':False,'configuration':{'harness_settings':{'model':'sonnet','permission_mode':'default','inherit_global_mcps':'disabled'},
        'session_policy':'per_sender','tool_access':'ask','authorization':{'minutes':60,'actions':3,'no_expiry':False,'unlimited_actions':False},
        'alias':P['profile'],'runtime_enabled':True}}

def test_exact_draft_and_changed_model_policy():
    assert validate_draft(draft(),P)
    for field,value in [('model','opus'),('permission_mode','bypassPermissions'),('inherit_global_mcps','enabled')]:
        d=draft();d['configuration']['harness_settings'][field]=value
        with pytest.raises(Refused):validate_draft(d,P)

def test_changed_server_or_request_refused():
    for field,value in [('server_origin','http://example.test'),('setup_run_id','old-codex-request')]:
        d=draft();d[field]=value
        with pytest.raises(Refused):validate_draft(d,P)

def test_inventory_requires_unique_exact_bytes(tmp_path):
    selected={'path':str(tmp_path/'claude.exe'),'sha256':'a'*64}
    row={'adapter_id':'claude_stream','executable':selected['path'],'fingerprint':'sha256:'+'a'*64}
    assert validate_inventory({'candidates':[row]},selected)['fingerprint']==row['fingerprint']
    for rows in ([],[row,row],[dict(row,fingerprint='sha256:'+'b'*64)]):
        with pytest.raises(Refused):validate_inventory({'candidates':rows},selected)

def test_actual_installed_wizard_sequence(monkeypatch):
    from nexus_connector_core import discover_harness_configuration
    from okto_nexus_connector.cli.commands.configure import template
    from okto_nexus_connector.cli.wizard_prompts import preferences,choice
    values=iter(['sonnet','1','2','3','2','1','60','3','1'])
    monkeypatch.setattr('builtins.input',lambda:next(values))
    cfg=preferences(template(),discover_harness_configuration('claude_stream'))
    assert cfg['harness_settings']==draft()['configuration']['harness_settings']
    assert cfg['authorization']==draft()['configuration']['authorization']
    assert cfg['session_policy']=='per_sender' and cfg['tool_access']=='ask'
    assert choice('Save this host draft for operator review?',[(True,'Save draft'),(False,'Cancel')],False) is True
    with pytest.raises(StopIteration):next(values)

def test_actual_isolated_entrypoint_help():
    entry=Path(__file__).with_name('onboarding_entry.py')
    result=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(entry),'--help'],capture_output=True)
    assert result.returncode==0 and b'{draft,plan}' in result.stdout

def test_actual_isolated_entrypoint_bad_pin_no_dispatch(tmp_path):
    entry=Path(__file__).with_name('onboarding_entry.py')
    result=subprocess.run([sys.executable,'-I','-B','-X','utf8',str(entry),'--plan',str(tmp_path/'none.json'),
        '--expected-plan-sha256','0'*64,'draft'],capture_output=True)
    assert result.returncode!=0 and b'ONBOARDING_PLAN_CHANGED' in result.stderr
