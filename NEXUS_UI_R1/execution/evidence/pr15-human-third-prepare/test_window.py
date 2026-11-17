import json,tempfile,unittest
from pathlib import Path
from observation_window import ObservationWindow

class ReadWindowTests(unittest.TestCase):
    def test_initial_sixty_minutes_expires_without_authority_effects(self):
        w=ObservationWindow(100,3600)
        self.assertFalse(w.expired(3699));self.assertTrue(w.expired(3700))

    def test_explicit_extension_is_once_per_identity_and_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'extend.json';p.write_text(json.dumps({'request_id':'facilitator-1','seconds':3600}))
            w=ObservationWindow(100,3600);r=w.consume(p,3600)
            self.assertEqual(r['status'],'EXTENDED_READ_WINDOW_ONLY');self.assertEqual(w.deadline,7300)
            self.assertIsNone(w.consume(p,3650))
            p.write_text(json.dumps({'request_id':'facilitator-1','seconds':1200}))
            self.assertEqual(w.consume(p,3660)['status'],'IGNORED_DUPLICATE');self.assertEqual(w.deadline,7300)

    def test_invalid_request_does_not_shorten_or_extend_window(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'extend.json';w=ObservationWindow(0,3600)
            for body in ('{invalid',json.dumps({'request_id':'bad','seconds':True}),json.dumps({'request_id':'bad','seconds':5000}),json.dumps({'request_id':'bad','seconds':60,'grant':True})):
                p.write_text(body);self.assertEqual(w.consume(p,100)['status'],'REJECTED_READ_WINDOW_EXTENSION');self.assertEqual(w.deadline,3600)

    def test_expired_window_cannot_be_resurrected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'extend.json';p.write_text(json.dumps({'request_id':'late','seconds':3600}));w=ObservationWindow(0,60)
            self.assertEqual(w.consume(p,61)['status'],'REJECTED_READ_WINDOW_EXTENSION');self.assertEqual(w.deadline,60)
if __name__=='__main__':unittest.main()
