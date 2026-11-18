"""Reuse base allocator unchanged except exact fixture-transform module selection."""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--gate', type=Path, required=True)
    args = parser.parse_args()
    load('h03_input_preparation_guard', HERE / 'validate.py').check(args.gate)
    base = load('unchanged_h03_allocator', BASE / 'prepare.py')
    original_module = base.module

    def module(name, path):
        if Path(path).resolve() == (BASE / 'fixture_transform.py').resolve():
            return original_module(name, HERE / 'fixture_transform.py')
        return original_module(name, path)

    base.module = module
    try:
        return base.main()
    finally:
        base.module = original_module


if __name__ == '__main__':
    main()
