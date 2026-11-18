"""Curate the exact two installed cuts; raw captured output stays in owned Temp."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

import psutil

HERE = Path(__file__).resolve().parent
ROOTS = ('gweb2v6c',)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ready = read(HERE/'READY.json')
    cuts = []
    for shard, suffix in enumerate(ROOTS):
        root = Path('C:/Users/jpamb/AppData/Local/Temp')/('nexus-hst-installed-'+suffix)
        result = read(root/'result.json')
        inventory = read(root/'reports/inventory.json')
        phases = [json.loads(line) for line in (root/'reports/phases.jsonl').read_text(encoding='utf-8').splitlines()]
        outcomes = Counter()
        phase_inventory = []
        for node in inventory['collected']:
            values = [phase for phase in phases if phase['nodeid'] == node]
            status = ('FAIL' if any(value['outcome']=='failed' for value in values) else
                'SKIP' if any(value['outcome']=='skipped' for value in values) else
                'PASS' if node in inventory['finished'] and any(value['phase']=='call' and value['outcome']=='passed' for value in values)
                else 'NOT_RUN')
            outcomes[status] += 1
            phase_inventory.append(dict(nodeid=node,status=status,phases=[{k:v for k,v in value.items() if k!='longrepr'} for value in values],
                raw_failure_sha256=[hashlib.sha256(value.get('longrepr','').encode()).hexdigest() for value in values if value['outcome']=='failed']))
        source_before, source_after = read(root/'source-before.json'), read(root/'source-after.json')
        payload_before, payload_after = read(root/'payload-before.json'), read(root/'payload-after.json')
        helpers_before, helpers_after = read(root/'copied-helpers-before.json'), read(root/'copied-helpers-after.json')
        copied = read(root/'copied-tests.json')
        copied_drift = [name for name,pin in copied.items() if sha(root/'tree'/name)!=pin]
        copied_source_mismatch = [name for name,pin in copied.items() if source_before.get(name.replace('\\','/'))!=pin]
        known_alive = []
        for info in result['known_processes']:
            try:
                process = psutil.Process(info['pid'])
                if process.create_time()==info['birth'] and process.exe()==info['exe']:
                    known_alive.append(info)
            except psutil.NoSuchProcess:
                pass
        helper_drift = [name for name,value in helpers_after.items() if
            value['source_sha256']!=helpers_before[name]['source_sha256'] or value['copied_sha256']!=helpers_before[name]['copied_sha256']]
        assert not (root/'tree/src').exists()
        clean = (result['exit_code']==0 and inventory['exitstatus']==0 and not outcomes['FAIL'] and not outcomes['NOT_RUN']
            and source_before==source_after and payload_before==payload_after and not helper_drift
            and not copied_drift and not copied_source_mismatch and not result['signals']
            and not result['timed_out'] and not result['forced'] and not known_alive and not result['remaining_known_processes'])
        target = HERE/('installed-shard-'+str(shard))
        target.mkdir(exist_ok=True)
        for name in ('result.json','source-before.json','source-after.json','payload-before.json','payload-after.json',
                'copied-tests.json','copied-helpers-before.json','copied-helpers-after.json'):
            shutil.copyfile(root/name,target/name)
        for name in ('inventory.json','collected.json','origins-start.json','origins-end.json'):
            shutil.copyfile(root/'reports'/name,target/name)
        (target/'phase-inventory.json').write_text(json.dumps(phase_inventory,indent=2)+'\n',encoding='utf-8')
        # Retain literal outcome/time/class/node attributes; captured logs and
        # failure payload text remain private in Temp, referenced by hashes.
        junit = ET.parse(root/'reports/tests.xml')
        suite = junit.getroot().find('testsuite')
        assert suite is not None
        for parent in junit.iter():
            for child in list(parent):
                if child.tag in {'system-out','system-err','properties'}:
                    parent.remove(child)
        for case in junit.iter('testcase'):
            for child in list(case):
                if child.tag in {'system-out','system-err','properties'}:
                    case.remove(child)
                elif child.tag in {'failure','error','skipped'}:
                    raw = ET.tostring(child,encoding='utf-8')
                    skip_reason = child.get('message') if child.tag == 'skipped' else None
                    child.attrib.clear()
                    child.set('raw_sha256',hashlib.sha256(raw).hexdigest())
                    if skip_reason is not None:
                        child.set('reason',skip_reason)
                    child.text = 'Raw diagnostic retained in the owned Temp reports; see literal phase inventory.'
        junit.write(target/'tests-sanitized.xml',encoding='utf-8',xml_declaration=True)
        report = dict(status='PASS_WITH_SKIPS' if clean and outcomes['SKIP'] else 'PASS' if clean else 'NOT_GREEN',
            root=str(root),shard=shard,counts={name:outcomes[name] for name in ('PASS','SKIP','FAIL','NOT_RUN')},collected=len(inventory['collected']),
            junit_errors=int(suite.get('errors','0')),junit_seconds=float(suite.get('time','0')),
            pytest_exit_code=result['exit_code'],source_pins=len(source_before),payload_files=len(payload_before),
            full_source_equal=source_before==source_after,full_payload_equal=payload_before==payload_after,
            copied_test_files=len(copied),copied_test_drift=copied_drift,copied_source_mismatch=copied_source_mismatch,
            helper_drift=helper_drift,signals=result['signals'],timed_out=result['timed_out'],forced=result['forced'],
            known_processes_still_alive=known_alive,
            origins='Every loaded Nexus/Core/Connector module must resolve inside the frozen installed prefix; see origins start/end.',
            raw_logs=dict(stdout_sha256=sha(root/'reports/stdout.log'),junit_sha256=sha(root/'reports/tests.xml'),copied=False),
            limits=['Functional browser and Root source Home regression ran concurrently; no benchmark claim.',
                'SKIP is non-execution; no PTY/POSIX/human/real harness qualification inferred.',
                'Installed pytest counts alone do not verify every complete HST acceptance scenario.',
                '250ms descendant sampling does not enumerate every short-lived child; nested-child provenance is separate.'])
        (target/'qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        cuts.append(report)
    totals = Counter()
    for cut in cuts:
        totals.update(cut['counts'])
    assert len(read(HERE/'installed-shard-0/collected.json')) == sum(totals.values())
    report = dict(at=datetime.now(timezone.utc).isoformat(),status=('PASS_INSTALLED_HOME_SCOPED_WITH_SKIPS' if totals['SKIP'] else 'PASS_INSTALLED_HOME_SCOPED') if all(cut['status'].startswith('PASS') for cut in cuts) else 'NOT_GREEN',
        source_commit=ready['source_commit'],wheel_sha256=ready['wheel_sha256'],counts=dict(totals),cuts=cuts,
        antecedents=[],
        source_assertions_rewritten=False,provider_calls=0,personal_prefix_changed=False)
    (HERE/'installed-qualification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],counts=dict(totals),report_sha256=sha(HERE/'installed-qualification.json'))))


if __name__=='__main__':
    main()
