"""Preserve attempt 1; build with user-site build tools, install locally."""
from pathlib import Path

original = Path(__file__).with_name('build_release.py')
source = original.read_text(encoding='utf-8')
source = source.replace(
    'ROOT = Path(__file__).resolve().parent',
    "ROOT = Path(__file__).resolve().parent / 'qualified'\nROOT.mkdir(exist_ok=False)")
source = source.replace("[sys.executable, '-I', '-m', 'build'", "[sys.executable, '-m', 'build'")
source = source.replace("'install', '--no-deps', '--no-index'",
                        "'install', '--ignore-installed', '--no-deps', '--no-index'")
exec(compile(source, str(original), 'exec'))
