from datetime import datetime,timezone,timedelta
import unittest
import xml.etree.ElementTree as ET
from automation_contract import EVENTS,NS,event_command,validate_window,recovery_task_xml,classify_event,automatic_wake_assessment

class Contract(unittest.TestCase):
    def test_exact_nonforcing_commands(self):
        self.assertEqual(event_command(EVENTS[1],r'C:\Windows\System32'),[r'C:\Windows\System32\shutdown.exe','/l'])
        self.assertEqual(event_command(EVENTS[2],r'C:\Windows\System32'),[r'C:\Windows\System32\shutdown.exe','/r','/t','0'])
        self.assertEqual(event_command(EVENTS[0],r'C:\Windows\System32')['arguments'],[False,False,False])
        with self.assertRaises(ValueError): event_command('03-shutdown-power-on-logon',r'C:\Windows\System32')
    def test_no_credentials_or_os_action_in_recovery_task(self):
        xml=recovery_task_xml('S-1-5-21-1-2-3-1001',r'C:\own path\pythonw.exe',r'C:\own path\recover.py',r'C:\own path\plan.json','a'*64)
        root=ET.fromstring(xml); n={'t':NS}
        self.assertEqual(root.findtext('.//t:LogonType',namespaces=n),'InteractiveToken')
        self.assertEqual(root.findtext('.//t:RunLevel',namespaces=n),'LeastPrivilege')
        self.assertEqual(root.findtext('.//t:WakeToRun',namespaces=n),'false')
        self.assertEqual(len(root.findall('t:Actions/*',n)),1)
        self.assertNotIn('shutdown',xml); self.assertNotIn('Password',xml)
    def test_window_blocks_replay_like_late_trigger_and_other_principal(self):
        now=datetime.now(timezone.utc)
        w={'event_id':EVENTS[1],'not_before_utc':now.isoformat(),'expires_utc':(now+timedelta(minutes=5)).isoformat(),
           'principal_sha256':'own','reviewed_event_selected':True,'no_force_apps':True,'automatic_next_event':False}
        self.assertEqual(validate_window(w,now,'own'),EVENTS[1])
        for at,who in [(now+timedelta(hours=1),'own'),(now,'other')]:
            with self.assertRaises(ValueError): validate_window(w,at,who)
    def test_logout_and_restart_distinct(self):
        a={'principal_sha256':'own','logon_authentication_id':'1','last_boot_up_time_dmtf':'boot1'}
        b={**a,'logon_authentication_id':'2'}
        self.assertTrue(classify_event(EVENTS[1],a,b)['event_observed'])
        self.assertFalse(classify_event(EVENTS[2],a,b)['event_observed'])
        b['last_boot_up_time_dmtf']='boot2'
        self.assertTrue(classify_event(EVENTS[2],a,b)['event_observed'])
        self.assertFalse(classify_event(EVENTS[1],a,b)['event_observed'])
    def test_suspend_needs_independent_event_observation(self):
        a={'principal_sha256':'own','logon_authentication_id':'1','last_boot_up_time_dmtf':'boot1'}
        self.assertFalse(classify_event(EVENTS[0],a,a)['event_observed'])
        self.assertTrue(classify_event(EVENTS[0],a,a,os_transition_observed=True)['event_observed'])
        missing={**a,'last_boot_up_time_dmtf':None,'logon_authentication_id':'2'}
        self.assertFalse(classify_event(EVENTS[1],{**a,'last_boot_up_time_dmtf':None},missing)['event_observed'])
    def test_modern_standby_does_not_infer_wake_support_from_ac_setting(self):
        result=automatic_wake_assessment(modern_standby=True,on_ac=True,wake_ac=1,wake_dc=0)
        self.assertTrue(result['policy_enabled']); self.assertFalse(result['timer_attempt_eligible'])
        self.assertFalse(result['automatic_wake_guaranteed'])

if __name__=='__main__': unittest.main()
