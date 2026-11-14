import hashlib,importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('helper',Path(__file__).with_name('continue_adoption.py'))
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
class Tests(unittest.TestCase):
    def test_reservation_is_preserved_byte_identically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'reservation.json';value={'state':'READ_ONLY_ADOPTION_RESERVED','model_admissions':0}
            path.write_text(json.dumps(value));before=path.read_bytes();calls=[]
            common=SimpleNamespace(require_tags=lambda value,context:None,public_save=lambda *args:calls.append(args))
            pin={'path':str(path),'sha256':h.sha(path)}
            h.preserve_reservation(common,None,'adopt-local-reserved.json',value,pin)
            self.assertEqual(path.read_bytes(),before);self.assertFalse(calls)
            h.preserve_reservation(common,None,'adopt-local-result.json',{},pin)
            self.assertEqual(len(calls),1)
    def test_different_reservation_is_refused(self):
        with self.assertRaisesRegex(RuntimeError,'RESERVATION_SEMANTICS_CHANGED'):
            h.preserve_reservation(None,None,'adopt-local-reserved.json',{'model_admissions':1},{})
    def test_status_retains_original_checks_and_only_timeout_changes(self):
        from okto_nexus.adapters.outbound.service_manager import inspection
        calls=[];home=Path('C:/owned/home');context=SimpleNamespace(P={'paths':{'server_home':str(home)}})
        selected={'pid':5132}
        def original(**kw):calls.append(kw);return selected
        def observe(ctx,component):
            return inspection.inspect_local_server(home=home,database=home/'nexus.db',host='127.0.0.1',port=58631,timeout=5)
        def same(a,b):self.assertEqual(a,b)
        observer=SimpleNamespace(status=observe,same_owner=same)
        with patch.object(inspection,'inspect_local_server',original):
            self.assertEqual(h.bounded_status(context,'nexus',observer,selected),selected)
            self.assertIs(inspection.inspect_local_server,original)
        self.assertEqual(calls[0]['timeout'],10);self.assertEqual(len(calls),1)
    def test_status_error_restores_original_transport(self):
        from okto_nexus.adapters.outbound.service_manager import inspection
        original=inspection.inspect_local_server
        observer=SimpleNamespace(status=lambda *args:(_ for _ in ()).throw(RuntimeError('NOT_READY')))
        with self.assertRaisesRegex(RuntimeError,'NOT_READY'):
            h.bounded_status(None,'nexus',observer,None)
        self.assertIs(inspection.inspect_local_server,original)
if __name__=='__main__':unittest.main()
