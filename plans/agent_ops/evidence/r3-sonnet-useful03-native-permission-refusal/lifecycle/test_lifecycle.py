from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('collector_recovery_lifecycle',Path(__file__).with_name('lifecycle.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class Guards(unittest.TestCase):
    def test_six_proofs_require_matching_births_and_exit(self):
        roles={'parent':{'pid':1,'birth':10},'launcher':{'pid':2,'birth':20},'child':{'pid':3,'birth':30}}
        proof={'physical_exit_confirmed':True,'force_used':False,
            'cohorts':{c:{'cohort':deepcopy(roles)} for c in ('nexus','connector')},
            'exits':{c:{r:dict(v,physical_exit=True,exit_code=0) for r,v in roles.items()} for c in ('nexus','connector')}}
        module.validate_exit(proof)
        for delta in ({'birth':31},{'physical_exit':False},{'exit_code':3}):
            changed=deepcopy(proof);changed['exits']['connector']['child'].update(delta)
            with self.assertRaises(RuntimeError):module.validate_exit(changed)

    def test_fresh_generation_requires_new_cycle_and_same_task(self):
        old={'generation':'old','cohort':{'cycle_id':'old'},'instance_id':'same',
             'task':{'name':'same','digest':'same'}}
        current=dict(old,generation='new',cohort={'cycle_id':'new'})
        module.validate_fresh(current,old)
        with self.assertRaises(RuntimeError):module.validate_fresh(dict(current,cohort=old['cohort']),old)
        with self.assertRaises(RuntimeError):module.validate_fresh(dict(current,task={'name':'same','digest':'different'}),old)


if __name__=='__main__':unittest.main()
