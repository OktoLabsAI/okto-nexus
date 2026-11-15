from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rotation_cli_compat as candidate


class Tests(unittest.TestCase):
    def test_actual_parser_maps_authorization_sha256_without_effects(self):
        calls = []
        def construct(*args):
            calls.append(args)
            return SimpleNamespace()
        executor = SimpleNamespace(Context=construct)
        common = ['--plan', 'plan', '--expected-plan-sha256', 'plan-sha', '--authorization-sha256', 'auth-sha']
        for action in ('approve-storage', 'transfer'):
            value = candidate.load_context(executor, argv=common+[action])
            self.assertEqual(value.action, action)
        value = candidate.load_context(executor, producer=True, argv=common)
        self.assertIsNone(value.action)
        self.assertEqual(calls, [('plan', 'plan-sha', 'auth-sha')]*3)

    def test_producer_dispatch_and_adapter_preserve_other_arguments(self):
        expected = candidate.sha(candidate.__file__)
        common = ['--plan', 'plan', '--expected-plan-sha256', 'plan-sha', '--authorization-sha256', 'auth-sha']
        executor = SimpleNamespace(Context=lambda *args: SimpleNamespace(arguments=args),
                                   load_context=None, transfer=None)
        producer = SimpleNamespace(main=lambda: executor.load_context(producer=True))
        with patch.object(candidate, 'sources', return_value=(executor, producer)):
            value = candidate.main(['--producer', '--expected-compat-sha256', expected, *common])
        self.assertEqual(value.arguments, ('plan', 'plan-sha', 'auth-sha'))
        self.assertIsNone(executor.load_context)
        context = SimpleNamespace(P={'runtime_pins': {'rotation_producer.py': {
            'path': str(candidate.HERE/'rotation_producer.py'),
            'sha256': candidate.ORIGINALS['rotation_producer.py']}}})
        original = ['python', '-I', '-B', '-X', 'utf8', str(candidate.HERE/'rotation_producer.py'), *common]
        observed = []
        other = object()
        candidate.adapt_transfer(context, lambda **kwargs: observed.append(kwargs),
            lambda ctx, fn: fn(producer_argv=original, consumer_argv=['same-consumer'], effect_guard=other), expected)
        value = observed[0]
        self.assertEqual(value['producer_argv'][:5], original[:5])
        self.assertEqual(value['producer_argv'][5:9], [str(Path(candidate.__file__).resolve()), '--producer', '--expected-compat-sha256', expected])
        self.assertEqual(value['producer_argv'][9:], original[6:])
        self.assertEqual(value['consumer_argv'], ['same-consumer'])
        self.assertIs(value['effect_guard'], other)


if __name__ == '__main__':
    unittest.main(verbosity=2)
