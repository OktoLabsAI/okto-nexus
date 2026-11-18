"""Input-origin-only wrapper; browser reader/assertions and installed app unchanged."""
import argparse
import importlib.util
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('h03_input_origin_guard', HERE / 'validate.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    before = guard.check(args.gate)
    text = (BASE / 'run.py').read_text()
    old = "str(HERE/'prepare.py')"
    assert text.count(old) == 1
    text = text.replace(old, "str(HERE/'private-origin-v2'/'prepare.py')", 1)
    driver = types.ModuleType('unchanged_h03_reader_with_input_origin_preparation')
    driver.__file__ = str(BASE / 'run.py')
    exec(compile(text, driver.__file__, 'exec'), driver.__dict__)
    original_write = driver.write
    allocation = []

    def write(path, value):
        original_write(path, value)
        if path.name == 'security-guard-before.json':
            allocation.append(path.parent)
            original_write(path.parent / 'input-origin-variant-before.json', before)

    driver.write = write
    result = None
    try:
        result = driver.main()
    finally:
        driver.write = original_write
        if allocation:
            try:
                after = guard.check(args.gate)
                unchanged = after == before
            except BaseException as error:
                after, unchanged = {'error_type': type(error).__name__}, False
            original_write(allocation[0] / 'input-origin-variant-after.json',
                           {'before': before, 'after': after, 'unchanged': unchanged})
            if not unchanged:
                result = 1
    return result if result is not None else 1


if __name__ == '__main__':
    raise SystemExit(main())
