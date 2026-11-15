import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from transition_proof import evaluate, companion, PROVIDER, NAMES

def row(i,r,t):return dict(provider=PROVIDER,event_id=i,version=1,record_id=r,utc=t,transition=NAMES[i])
def samples():
    anchor=row(507,9,'2026-11-15T16:00:00Z')
    before=dict(status='READ_ONLY_CAPTURED',truncated=False,event_generated=False,boot_utc='2026-11-12T00:00:00Z',
      started_utc='2026-11-15T16:10:01Z',finished_utc='2026-11-15T16:10:02Z',latest=anchor)
    after=dict(status='READ_ONLY_CAPTURED',truncated=False,event_generated=False,boot_utc=before['boot_utc'],
      query_start_utc=before['started_utc'],query_end_utc='2026-11-15T16:12:00Z',anchor=anchor,
      manifest=[dict(provider=PROVIDER,event_id=i,version=1,log='System',transition=n) for i,n in NAMES.items()],
      events=[row(506,10,'2026-11-15T16:10:05Z'),row(507,11,'2026-11-15T16:11:30Z')])
    return before,after
def evaluate_pair(b,a):return evaluate(b,a,'2026-11-15T16:10:04Z','2026-11-15T16:20:00Z')

class ProofTests(unittest.TestCase):
    def test_exact_modern_pair_and_generic_pair(self):
        b,a=samples()
        self.assertTrue(evaluate_pair(b,a)['os_transition_observed'])
        a['events']=[row(42,10,'2026-11-15T16:10:05Z'),row(107,11,'2026-11-15T16:11:30Z')]
        out=evaluate_pair(b,a)
        self.assertTrue(out['os_transition_observed']);self.assertFalse(out['deep_power_residency_proven'])

    def test_missing_ambiguous_foreign_stale_and_changed_boot_fail_closed(self):
        for label in ('missing','truncated','foreign','stale','boot','anchor','manifest','multiple','mixed'):
            with self.subTest(label=label):
                b,a=samples()
                if label=='missing':a['events'].pop()
                elif label=='truncated':a['truncated']=True
                elif label=='foreign':a['events'][0]['provider']='Other'
                elif label=='stale':a['events'][0]['utc']='2026-11-15T16:10:03Z'
                elif label=='boot':a['boot_utc']='2026-11-15T16:11:00Z'
                elif label=='anchor':a['anchor']=None
                elif label=='manifest':a['manifest']=[]
                elif label=='multiple':a['events'].append(row(506,12,'2026-11-15T16:11:35Z'))
                elif label=='mixed':a['events'][1]=row(107,11,'2026-11-15T16:11:30Z')
                self.assertFalse(evaluate_pair(b,a)['os_transition_observed'])

    def test_real_ancestor_attempt_and_after_pin_binding(self):
        import sys
        from transition_proof import ANCESTOR
        sys.path.insert(0,str(ANCESTOR))
        from automation_contract import event_command
        pb,pa=samples()
        own=dict(principal_sha256='a'*64,logon_authentication_id='synthetic',last_boot_up_time_dmtf='syntheticboot')
        window=dict(event_id='01-suspend-resume',not_before_utc='2026-11-15T16:10:00+00:00',expires_utc='2026-11-15T16:20:00+00:00',
          principal_sha256='a'*64,reviewed_event_selected=True,no_force_apps=True,automatic_next_event=False)
        with tempfile.TemporaryDirectory() as d:
            def save(n,v):
                p=Path(d)/n;p.write_text(json.dumps(v),encoding='utf-8');return p,hashlib.sha256(p.read_bytes()).hexdigest()
            plan,ps=save('plan.json',dict(selected_event='01-suspend-resume',window=window))
            before,bs=save('before.json',dict(plan_sha256=ps,event_id='01-suspend-resume',own_session=own,utc='2026-11-15T16:10:00Z'))
            attempt,ats=save('attempt.json',dict(state='RESERVED_BEFORE_OS_CALL',plan_sha256=ps,before_sha256=bs,
              event_id='01-suspend-resume',principal_sha256='a'*64,window=window,issued_utc='2026-11-15T16:10:04Z',
              command=event_command('01-suspend-resume',r'C:\Windows\System32'),automatic_next_event=False,no_force_apps=True,no_retry=True))
            after,av=save('after.json',dict(plan_sha256=ps,before_sha256=bs,event_id='01-suspend-resume',event_attempt_pin={'sha256':ats},current={'own_session':own}))
            bp,_=save('power-before.json',pb);ap,_=save('power-after.json',pa)
            self.assertTrue(companion(plan,ps,before,after,attempt,bp,ap)['correlated_assessment']['event_observed'])
            bad=json.loads(after.read_bytes());bad['event_attempt_pin']['sha256']='0'*64;save('after.json',bad)
            with self.assertRaisesRegex(ValueError,'AFTER_SCOPE_CHANGED'):companion(plan,ps,before,after,attempt,bp,ap)

if __name__=='__main__':unittest.main()
