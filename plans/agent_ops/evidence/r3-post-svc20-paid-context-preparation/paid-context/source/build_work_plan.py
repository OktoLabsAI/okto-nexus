"""Bind completed public configuration and offline code; no service/provider IO."""
from pathlib import Path
import json
import sys
import hashlib
HERE=Path(__file__).resolve().parent
RECOVERY=Path('C:/Users/jpamb/AppData/Local/Temp/sonnet-canonical-recovery-proposal-7oq808_t')
sys.path.insert(0,str(HERE))
from request_context import read_json,require
from work_context import WORK_IDS

def pin(path):
    p=Path(path);return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}

def main():
    require(not (HERE/'work-plan.json').exists(),'WORK_PLAN_ALREADY_EXISTS')
    phase=read_json(RECOVERY/'lifecycle-plan.json');binding=read_json(RECOVERY/'binding02-plan.json')
    root=Path(phase['campaign_root']);public=RECOVERY/'public'
    completed=read_json(public/'recovery02-profile-completed.json')
    profile=Path(phase['paths']['operator_home'])/'terminal/profiles'/(binding['profile']+'.json')
    require(pin(profile)['sha256']==completed['profile_sha256'],'COMPLETED_PROFILE_CHANGED')
    post=RECOVERY/'post-svc20';post_freeze=read_json(post/'runtime-freeze.json')
    prerequisites={name:pin(public/filename) for name,filename in {
        'completed_profile':'recovery02-profile-completed.json','rotation_result':'rotation-import-result.json',
        'canonical_review':'recovery02-review.json',
        'nexus_selection':'nexus-owner-selection.json','nexus_watch_started':'nexus-exit-watch-started.json'}.items()}
    prerequisites.update({name:pin(post/'public'/filename) for name,filename in {
        'connector_selection':'connector-owner-selection.json','connector_watch_started':'connector-exit-watch-started.json'}.items()})
    rotation=read_json(binding['rotation_plan']['path'])
    prerequisites['rotation_authority']=pin(rotation['authorization_receipt'])
    prerequisites['original_failed_transfer']=binding['pins']['old_failed_transfer']
    project=Path(phase['paths']['connector_project']);report=root/'campaign/deliverables/remote/report.json'
    require(not report.exists() and report.parent.is_dir(),'NEW_REPORT_LOCATION_REQUIRED')
    source=pin(project/'numbers.csv')
    require(source['sha256']=='876c1313400238ba1b78cc54fab94411c28b74d2c592c69422eb89800f634d4b','INPUT_FIXTURE_CHANGED')
    rtk=pin('C:/Users/jpamb/AppData/Local/Microsoft/WinGet/Packages/rtk-ai.rtk_Microsoft.Winget.Source_8wekyb3d8bbwe/rtk.exe')
    require(rtk['sha256']=='941654cc74ced3e773fa0cef43b044a4717c6884a429bfb14db50093defa38fb','RTK_CHANGED')
    python=pin(phase['python'])
    console=pin('C:/Users/jpamb/AppData/Local/Temp/r3-svc09-console-watch-y0edb3e0/console_watch.py')
    require(console['sha256']=='7d23cff5ae6ad32a2d0084ae59cdb35ae61a8a9f60ffcedbf1b941369d0a65fd','CONSOLE_HELPER_CHANGED')
    argv=['-I','-B','-X','utf8','-m','okto_nexus_connector.cli.main','--json','--state-dir',phase['paths']['connector_state'],'daemon','stop','--timeout','45']
    useful=(f"Read only {project.as_posix()}/numbers.csv. Calculate its data row count, sum and SHA-256. "
        f"Write exactly one JSON object with keys row_count, sum and input_sha256 to {report.as_posix()}. "
        "The report directory is precreated outside the approved project writable root but inside this disposable campaign root. "
        "Do not change permissions, sandbox, writable roots or global policy. If the actual native policy requires permission, "
        "request it through the native mechanism and wait for the human decision. Do not read or write other data paths, use the network, "
        "install tools, spawn subagents or retry a denied command using another method. Use one noninteractive Python process "
        f"through the approved absolute RTK executable '{Path(rtk['path']).as_posix()}' proxy '{Path(python['path']).as_posix()}' "
        "-c '<single-line Python code computed by you>'. Use quoting appropriate to the actual native shell, with no nested PowerShell "
        "or shell-expanded variables. The two named executables are approved execution dependencies, not extra data inputs. "
        "Compute the result from the CSV; no expected values are supplied. In that same Python process print the computed JSON to stdout "
        "after writing it. Include that same computed JSON in your final assistant response so it becomes the canonical result.")
    p={'scope':'TWO_REMOTE_SONNET_WORK_CALLS_NO_SETUP_REPLAY','model':'sonnet','request_ids':WORK_IDS,
        'budget':{'limit':200000,'preventive':150000,'initial_reserve':50000,'next_input_multiplier':2,'next_output_margin':32000},
        'root_retains_observers':True,'recovery_plan':pin(RECOVERY/'lifecycle-plan.json'),
        'binding_plan':pin(RECOVERY/'binding02-plan.json'),
        'post_svc20_plan':pin(post/'selected-plan.json'),'post_svc20_freeze':pin(post/'runtime-freeze.json'),
        'post_svc20_context_source':post_freeze['files']['post_context.py'],
        'work_runtime_freeze':pin(HERE/'work-runtime-freeze.json'),'prerequisites':prerequisites,
        'runtime_pins':{n:pin(HERE/n) for n in ('work_context.py','work-entry.py')},
        'server_id':binding['server_id'],'profile':binding['profile'],'operator_profile':binding['operator_profile'],
        'agent_id':binding['agent_id'],'candidate_ref':completed['remote_scope']['candidate_ref'],
        'project':str(project),'report':str(report),'input_fixture':source,'rtk':rtk,'python_executable':python,'console_helper':console,
        'prompts':{'useful':useful,'continuation':'Using only the existing canonical result in this same session, state the reported sum once. Do not run another command or write another file.'},
        'normal_stop_argv':{'connector':[phase['python'],*argv],
            'nexus':next(s['argv'] for s in phase['commands']['steps'] if s['component']=='nexus' and s['action']=='stop')},
        'authority':'Technical binding of existing user permission for authenticated Claude Sonnet with separate200k tokens; no new user hash approval. Root reviews this exact finite selection before work.',
        'accounting':'Initial50000 reserve; later max(50000,2*previous observed input including cache+32000), total+reserve<=150000; complete fresh accounting required.200000 observed limit is not an atomic provider token cap.',
        'setup_turn':'Not selected: completed canonical onboarding required and no setup:test or exploratory turn in this workflow.',
        'permission':'Use actual native permission path only. No fabricated question or personal-policy override; absence of pending permission is recorded honestly.',
        'svc09':'Root selected one conditional console hook at first actual native question after events worker joined. Existing qualified5s watch self-exits; exact bothcohort/sameop observation before/after; no approval while consoleopen. Invisible window alone inconclusive, not DX40failure. Root separately closes own dashboard. Pending launcher/runtime stays retained and never races profileCLI.',
        'participant_boundary':'Installed real CLI participant refusal fixture proves authorization negative; actual campaign must retain agent-only transfer and human operator decision provenance. No live credential extraction/abuse probe is selected.',
        'cleanup':'One exact normal stop per component, noforce; six retained query handles and Root external observers. Unknown worker/physical exit produces explicit parent handoff, never settlement claim.'}
    (HERE/'work-plan.json').write_text(json.dumps(p,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(pin(HERE/'work-plan.json')))

if __name__=='__main__':main()
