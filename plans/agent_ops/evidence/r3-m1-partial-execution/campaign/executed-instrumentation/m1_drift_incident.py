from pathlib import Path
import hashlib,json,ntpath,time
from okto_nexus.application import terminal_connection
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-campaign-refresh-0ssbo8pb/m1-campaign')
observed=json.loads((root/'public/profile-drift-readonly.json').read_text())
setup=json.loads((root/'public/local-setup-result.json').read_text())
selection,folders,connection=observed['selection'],observed['folders'],observed['connection']
checks={'binding_present':bool(connection),'execution_location_local':connection['execution_location']=='local',
        'adapter_matches':connection['adapter_id']=='codex_app_server',
        'workspace_selection_absent_or_equal':selection['workspace_id'] is None or selection['workspace_id']==connection['workspace_id'],
        'candidate_matches':selection['candidate_ref']==connection['candidate_ref'],
        'project_raw_matches':selection['project']==folders['workspace_root'],
        'provider_raw_matches':selection['provider_home']==folders['provider_home'],
        'provider_windows_lexical_matches':ntpath.normcase(ntpath.normpath(selection['provider_home']))==ntpath.normcase(ntpath.normpath(folders['provider_home']))}
assert all(v for k,v in checks.items() if k!='provider_raw_matches') and not checks['provider_raw_matches']
source=Path(terminal_connection.__file__)
result={'recorded_at':time.time(),'classification':'PRODUCT_FALSE_PROFILE_DRIFT_WINDOWS_PATH_SEPARATORS',
        'installed_source':str(source),'installed_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_lines':'TerminalConnection.observe lines 172-175',
        'predicate_results':checks,'native_setup_terminal':setup['monitor']['result_stage'],
        'observed_tokens_minimum':setup['summary']['known_observed_tokens'],'global_reserved_requests':1,
        'poll_max_seconds':setup['maximum_poll_start_interval_seconds'],
        'setup_profile_state':'done','finish_saved':True,'binding_state':'APPROVED',
        'campaign_state':'SAFE_PENDING_NO_NEW_ADMISSIONS','productive_work_started':False,
        'connector_installed':False,'setup_replayed':False,'profile_mutated_for_recovery':False,
        'native_setup_close_stage':setup['monitor']['close_stage'],'owned_slot_released':setup['monitor']['owned_slot_released'],
        'limits':['Native setup is a real charged inference; observed counter is not billed or final.',
                  'No local useful task, native decision, continuity or Connector M1 result was qualified.',
                  'Original pinned package and retained receipts must remain attributable; any corrected package needs explicit review.']}
(root/'public/profile-drift-incident.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'classification':result['classification'],'source_sha256':result['installed_source_sha256'],'checks':checks}))
