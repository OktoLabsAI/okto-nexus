import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as S
import unittest
from unittest.mock import Mock
import collect

class Collector(unittest.TestCase):
    def test_unselected_plan_refuses_before_import_or_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'plan.json';p.write_text(json.dumps({'selected_event':None}))
            with self.assertRaisesRegex(ValueError,'EVENT_WINDOW_NOT_SELECTED'):
                collect.load(p,collect.digest(p))

    def test_actual_history_compared_without_forged_manual_marker_or_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            event='02-sign-out-logon';directory=Path(temp)/'evidence'/event;directory.mkdir(parents=True)
            own={'principal_sha256':'own','logon_authentication_id':'old','last_boot_up_time_dmtf':'boot'}
            component={'task':{'digest':'task'}}
            old={'plan_sha256':'plan','history':{'real':'before'},'own_session':own,'components':{'nexus':component,'connector':component}}
            (directory/'before.json').write_text(json.dumps(old))
            current={'own_session':{**own,'logon_authentication_id':'new'},'components':old['components']}
            H=S(capture=Mock(return_value={'real':'after'}),compare=Mock(return_value={'status':'ACTUAL_CHANGE'}))
            N=S(snapshot=Mock(return_value=(current,{})))
            saved={}
            O=S(read=lambda p:json.loads(Path(p).read_bytes()),NAMES=('nexus','connector'),ready=lambda c:True,
                old_shutdown=lambda a,b:{'state':'UNKNOWN'},logon_correlation=lambda a,b,n:False,
                save=lambda p,v:saved.update({Path(p).name:v}))
            P={'selected_event':event,'root':temp,'task_digests':{'nexus':'task','connector':'task'}}
            result=collect.after(P,N,O,H,'plan')
            H.compare.assert_called_once_with({'real':'before'},{'real':'after'})
            self.assertTrue(result['event_observed'])
            value=saved['after.json'];self.assertNotIn('performed_by_user',json.dumps(value))
            self.assertEqual(value['assessment']['prior_generation_physical_exit'],'UNKNOWN')
            self.assertEqual(value['assessment']['history']['status'],'ACTUAL_CHANGE')
            # A reserved-but-not-published interrupted collection is not replayed.
            with self.assertRaises(FileExistsError):collect.after(P,N,O,H,'plan')
            self.assertEqual(N.snapshot.call_count,1)

if __name__=='__main__':unittest.main()
