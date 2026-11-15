from pathlib import Path
import sys, json, datetime
sys.path.insert(0, str(Path(__file__).resolve().parent))
from recovery_context import RecoveryContext, require, read_json, sha, reserve
from recovery_observation import capture, same_cycle, Process
root = Path(__file__).resolve().parent
x = RecoveryContext(root/'lifecycle-plan.json', '8980570ab636b7836ffa34a5976652c0cc19825af015c50d50a9c5b08bcf6a27')
old = read_json(x.PUBLIC/'nexus-owner-selection.json')
started = read_json(x.PUBLIC/'nexus-exit-watch-started.json')
timeout = read_json(x.PUBLIC/'nexus-exit-watch-timeout.json')
x.require_tags(old); x.require_tags(started); x.require_tags(timeout)
require(started['cohort'] == old['cohort'] and timeout['cohort'] == old['cohort'], 'ORIGINAL_COHORT_CHANGED')
require(timeout['physical_exit_confirmed'] is False, 'TIMEOUT_REQUIRED')
require(not (x.PUBLIC/'nexus-exit-proof.json').exists(), 'EXIT_ALREADY_OBSERVED')
# The root also observed execution session62571 terminal(exit1), tool10a2cd.
try:
    observer = Process(started['observer']['pid'])
except Exception:
    observer = None
if observer is not None:
    try:
        require(observer.birth != started['observer']['birth'], 'ORIGINAL_OBSERVER_STILL_LIVE')
    finally:
        observer.close()
current, handles = capture(x)
try:
    same_cycle(old['cohort'], current['cohort'])
    require(all(current[k] == old[k] for k in ('pid','generation','instance_id')), 'OWNER_CHANGED')
    archive = x.PUBLIC/'nexus-observer-expired-01'
    require(archive.resolve().is_relative_to(x.PUBLIC.resolve()), 'ARCHIVE_OUTSIDE_SCOPE')
    archive.mkdir(exist_ok=False)
    files = []
    for name in ('nexus-exit-watch-started.json','nexus-exit-watch-timeout.json'):
        source, destination = x.PUBLIC/name, archive/name
        require(source.resolve().is_relative_to(x.PUBLIC.resolve()) and destination.resolve().is_relative_to(archive.resolve()), 'MOVE_OUTSIDE_SCOPE')
        digest = sha(source)
        source.rename(destination)
        require(sha(destination) == digest, 'ARCHIVE_HASH_CHANGED')
        files.append({'original_path': str(source), 'archive_path': str(destination), 'sha256': digest})
    reserve(x.PUBLIC/'nexus-observer-refresh-selection.json', {
        'status':'SAME_COHORT_OBSERVATION_REFRESH_SELECTED', 'expired_session':62571,
        'terminal_observation_tool':'10a2cd', 'archived':files,
        'generation':old['generation'], 'cohort':old['cohort'],
        'service_actions':0, 'provider_calls':0,
        'recorded_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    print(json.dumps({'status':'SAME_COHORT_OBSERVATION_REFRESH_SELECTED','service_actions':0}))
finally:
    for h in handles.values(): h.close()
