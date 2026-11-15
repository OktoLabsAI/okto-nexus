from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile,unittest
from types import SimpleNamespace as S
from unittest.mock import Mock
from attempt_contract import digest
from execute_event import execute
from collect import after

class Handle:
    def exited(self):return False
    def close(self):pass

class Attempt(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=datetime(2026,11,15,17,tzinfo=timezone.utc);event='02-sign-out-logon'
        self.P={'root':self.temp.name,'selected_event':event,'window':{'event_id':event,'principal_sha256':'own',
            'not_before_utc':(self.now-timedelta(minutes=1)).isoformat(),'expires_utc':(self.now+timedelta(minutes=5)).isoformat(),
            'reviewed_event_selected':True,'no_force_apps':True,'automatic_next_event':False},
            'task_digests':{'nexus':'n','connector':'c'}}
        self.directory=Path(self.temp.name)/'evidence'/event;self.directory.mkdir(parents=True)
        components={}
        for i,name in enumerate(('nexus','connector')):
            components[name]={'task':{'digest':name[0]},'canonical':{'pid':10+i,'generation':name,'instance_id':name},
                'cohort':{role:{'pid':100+i*3+j,'birth':200+i*3+j} for j,role in enumerate(('parent','launcher','child'))}}
        self.old={'event_id':event,'utc':(self.now-timedelta(seconds=30)).isoformat(),'plan_sha256':'plan',
            'own_session':{'principal_sha256':'own','logon_authentication_id':'old','last_boot_up_time_dmtf':'boot'},
            'components':components,'history':{'old':True}}
        self.write(self.directory/'before.json',self.old)
        def expected(v):return {name+'/'+role:meta for name,c in v['components'].items() for role,meta in c['cohort'].items()}
        self.handles={key:Handle() for key in expected(self.old)}
        self.N=S(snapshot=Mock(return_value=(deepcopy(self.old),self.handles)))
        self.O=S(NAMES=('nexus','connector'),read=lambda p:json.loads(Path(p).read_bytes()),save=self.write,
            ready=lambda c:True,expected_handles=expected,old_shutdown=lambda a,b:{'state':'UNKNOWN'},logon_correlation=lambda a,b,n:False)
        self.H=S(capture=Mock(return_value={'new':True}),compare=lambda a,b:{'status':'HISTORY_COMPARED'})
        self.dispatch=Mock(return_value={'command_return_code':0,'event_proven':False})
    @staticmethod
    def write(p,v):
        with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f)
        return digest(p)
    def run_event(self,**kw):return execute(self.P,self.N,self.O,'plan',clock=lambda:self.now,dispatch=self.dispatch,**kw)
    def test_unrelated_logon_without_attempt_cannot_consume_after(self):
        self.assertEqual(after(self.P,self.N,self.O,self.H,'plan')['status'],'NO_SELECTED_EVENT_ATTEMPT_NO_AFTER_RESERVATION')
        self.assertFalse((self.directory/'after.reserved').exists());self.N.snapshot.assert_not_called()
    def test_wrong_pins_principal_and_window_refused_before_after_reservation(self):
        self.run_event();path=self.directory/'event-attempt.json';original=json.loads(path.read_bytes())
        for field,value in [('plan_sha256','wrong'),('before_sha256','wrong'),('event_id','04-restart-logon'),
                            ('principal_sha256','other'),('issued_utc',(self.now+timedelta(hours=1)).isoformat())]:
            altered=deepcopy(original);altered[field]=value;path.write_text(json.dumps(altered))
            with self.assertRaises(ValueError):after(self.P,self.N,self.O,self.H,'plan')
            self.assertFalse((self.directory/'after.reserved').exists())
        path.write_text(json.dumps(original))
    def test_expired_or_changed_owner_never_dispatches(self):
        self.P['window']['expires_utc']=(self.now-timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):self.run_event()
        self.dispatch.assert_not_called();self.assertFalse((self.directory/'event-attempt.json').exists())
        self.P['window']['expires_utc']=(self.now+timedelta(minutes=1)).isoformat()
        current=deepcopy(self.old);current['components']['nexus']['cohort']['child']['birth']+=1
        self.N.snapshot.return_value=(current,self.handles)
        with self.assertRaises(ValueError):self.run_event()
        self.dispatch.assert_not_called()
    def test_legitimate_attempt_is_once_then_correlated_after_not_returncode_proof(self):
        result=self.run_event();self.assertFalse(result['event_proven']);self.dispatch.assert_called_once()
        with self.assertRaises(ValueError):self.run_event()
        self.assertEqual(self.dispatch.call_count,1)
        current=deepcopy(self.old);current['own_session']['logon_authentication_id']='new'
        self.N.snapshot.return_value=(current,{})
        result=after(self.P,self.N,self.O,self.H,'plan');self.assertTrue(result['event_observed'])
        retained=json.loads((self.directory/'after.json').read_bytes())
        self.assertEqual(retained['event_attempt_pin']['sha256'],digest(self.directory/'event-attempt.json'))
        self.assertFalse(retained['assessment']['physical_exit_inferred'])
        self.assertNotIn('performed_by_user',json.dumps(retained))
        self.assertEqual(after(self.P,self.N,self.O,self.H,'plan')['status'],'AFTER_ALREADY_RECORDED_NO_REPLAY')
    def test_expiry_after_reservation_consumes_attempt_without_effect_or_after(self):
        moments=iter([self.now,self.now+timedelta(hours=1)])
        with self.assertRaises(ValueError):execute(self.P,self.N,self.O,'plan',clock=lambda:next(moments),dispatch=self.dispatch)
        self.dispatch.assert_not_called();self.assertTrue((self.directory/'event-attempt.json').exists())
        self.assertEqual(after(self.P,self.N,self.O,self.H,'plan')['status'],'NO_SELECTED_EVENT_ATTEMPT_NO_AFTER_RESERVATION')
        self.assertFalse((self.directory/'after.reserved').exists())
    def test_unknown_command_is_consumed_and_never_retried(self):
        self.dispatch.side_effect=OSError('fixture only')
        with self.assertRaises(OSError):self.run_event()
        with self.assertRaises(ValueError):self.run_event()
        self.assertEqual(self.dispatch.call_count,1)
        value=json.loads((self.directory/'event-command-returned.json').read_bytes())
        self.assertEqual(value['state'],'COMMAND_UNCONFIRMED');self.assertFalse(value['event_proven'])

if __name__=='__main__':unittest.main()
