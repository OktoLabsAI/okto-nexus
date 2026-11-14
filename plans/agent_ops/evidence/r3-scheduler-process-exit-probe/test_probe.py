import importlib.util
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('probe', ROOT / 'run.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class DefinitionTests(unittest.TestCase):
    def check_case(self, case):
        value = probe.definition(case, 'S-1-5-21-123-456-789-1001', '2026-11-14T20:00:00+00:00')
        root = ET.fromstring(value)
        ns = {'t': probe.NS}
        def text(path):
            return root.find(path, ns).text
        self.assertEqual(text('t:Settings/t:RestartOnFailure/t:Interval'), 'PT1M')
        self.assertEqual(text('t:Settings/t:RestartOnFailure/t:Count'), '1')
        self.assertEqual(text('t:Settings/t:AllowHardTerminate'), 'false')
        self.assertEqual(text('t:Settings/t:MultipleInstancesPolicy'), 'IgnoreNew')
        self.assertEqual(text('t:Actions/t:Exec/t:Command'), str(probe.ACTION_PYTHONW))
        self.assertEqual(probe.ACTION_PYTHONW.name, 'pythonw.exe')
        arguments = text('t:Actions/t:Exec/t:Arguments')
        self.assertTrue(arguments.startswith('-I -B -X utf8 '))
        self.assertTrue(arguments.endswith(case))
        self.assertEqual(len(root.findall('t:Triggers/t:TimeTrigger', ns)), int(case.startswith('timer-')))
        self.assertEqual(len(root.findall('t:Actions/t:Exec', ns)), 1)
        self.assertEqual(probe.digest(value), probe.digest(value))

    def test_manual_3(self): self.check_case('manual-3')
    def test_manual_ffffffff(self): self.check_case('manual-ffffffff')
    def test_timer_3(self): self.check_case('timer-3')
    def test_timer_ffffffff(self): self.check_case('timer-ffffffff')

if __name__ == '__main__':
    unittest.main()
