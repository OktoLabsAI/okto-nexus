"""Offline metadata only; never imports the executable probe."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
python = Path('C:/Users/jpamb/AppData/Local/Temp/r3-native-t19-t20-39ycaumc/venv/Scripts/python.exe')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
plan = {
    'status': 'PREPARED_NOT_EXECUTED_ROOT_REVIEW_REQUIRED',
    'purpose': 'Isolate Windows Scheduler process exit code and trigger semantics after inconclusive T19 crash recovery.',
    'root': str(root),
    'cases': [
        {'case': case, 'task_name': 'OktoT19-SchedulerProbe-7bg9yatu-' + case,
         'trigger': 'Run(None)' if case.startswith('manual') else 'single TimeTrigger UTC boundary 30 seconds ahead',
         'action_exit_dword': 3 if case.endswith('-3') else 4294967295}
        for case in ('manual-3', 'manual-ffffffff', 'timer-3', 'timer-ffffffff')],
    'restart_interval': 'PT1M', 'restart_count': 1,
    'observation_seconds_after_latest_dispatch_or_boundary': 135,
    'selected_failure_actions_max_per_case': 2,
    'unexpected_extra_native_launch': 'receipt is preserved; action exits 0 instead of inducing another failure; experiment reports ATTEMPT_COUNT_UNCONFIRMED',
    'effects': ['create four absent-only current-user interactive least-privilege own tasks',
               'invoke Run(None) once for each manual task; timer tasks have one automatic boundary',
               'actions write only owned PID/birth/time/intended-exit receipts; no subprocess, network or product import',
               'retained query/synchronize handles verify exact birth and actual exit; no terminate right',
               'delete unchanged inactive own tasks after observation; retain all files; no stop/force'],
    'no_effects': ['product services', 'provider calls', 'login or credentials', 'personal task enumeration or mutation', 'global TaskScheduler settings or event logging changes'],
    'caveats': ['COM calls and OS I/O are not preemptible by the observation timer',
                'Count=1 is an OS policy under test, not an assertion that Windows cannot launch an unexpected third guard action',
                'matrix results describe this host; no general retry exhaustion claim'],
    'action_pythonw': str(python.with_name('pythonw.exe')),
    'pins': [{'path': str(p), 'sha256': sha(p)} for p in [root/'run.py',root/'action.py',python,python.with_name('pythonw.exe'),Path('C:/Python313/python.exe'),Path('C:/Python313/pythonw.exe')]],
    'offline_qualification': {'cases': 4, 'passed': 4, 'initial_tool_chunk': '4ff3a6', 'pythonw_delta_log': 'pythonw-xml-tests.txt', 'no_tasks_or_actions_executed': True},
    'command': [str(python), '-I', '-B', '-X', 'utf8', str(root/'run.py'), '--execute-reviewed', '--plan-sha256', '<SHA256_OF_THIS_PLAN>'],
}
(root/'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True), encoding='utf-8')
print(json.dumps({'root':str(root),'plan_sha256':sha(root/'plan.json'),'run_sha256':sha(root/'run.py'),'action_sha256':sha(root/'action.py')}))
