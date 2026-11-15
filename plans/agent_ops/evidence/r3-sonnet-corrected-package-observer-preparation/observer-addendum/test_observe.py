from pathlib import Path
from types import SimpleNamespace
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from observe import exact_handle,wait_for_exits,sha,ROLES

class Tests(unittest.TestCase):
    def test_birth_mismatch_refuses_same_pid_without_control(self):
        with tempfile.TemporaryDirectory() as directory:
            image=Path(directory)/'synthetic-image';image.write_bytes(b'fixture')
            h=SimpleNamespace(pid=39640,birth=9,image=str(image),exited=lambda:False)
            with self.assertRaisesRegex(RuntimeError,'EXACT_LIVE_PROCESS_REQUIRED'):
                exact_handle(h,{'pid':39640,'birth':8},{str(image):sha(image)})
            exact_handle(h,{'pid':39640,'birth':9},{str(image):sha(image)})

    def test_timeout_is_not_exit_and_success_does_not_assert_force(self):
        now=[0.0];dead=[False]
        def sleep(seconds):now[0]+=seconds
        hs={r:SimpleNamespace(pid=i+1,birth=i+10,exited=lambda:dead[0],exit_code=lambda:0)
            for i,r in enumerate(ROLES)}
        result=wait_for_exits(hs,.5,clock=lambda:now[0],sleep=sleep)
        self.assertEqual(result,{'physical_exit_confirmed':False})
        dead[0]=True
        result=wait_for_exits(hs,.5,clock=lambda:now[0],sleep=sleep)
        self.assertTrue(result['physical_exit_confirmed'])
        self.assertEqual(set(result['exits']),set(ROLES))
        self.assertNotIn('force_used',result)
        with self.assertRaises(RuntimeError):wait_for_exits({},1,clock=lambda:0,sleep=sleep)

if __name__=='__main__':unittest.main(verbosity=2)
