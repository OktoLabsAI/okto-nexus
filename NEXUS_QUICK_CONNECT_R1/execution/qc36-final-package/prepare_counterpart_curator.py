from pathlib import Path

HERE = Path(__file__).resolve().parent
source = (HERE / 'curate_regression.py').read_text(encoding='utf-8')
old = "choices=['installed-shard-0','installed-shard-1','installed-legacy']"
assert old in source
source = source.replace(old, "choices=['installed-shard-1-provider-focal','installed-shard-1-counterpart']")
(HERE / 'curate_shard1_counterpart.py').write_text(source, encoding='utf-8')
print('Prepared counterpart namespaces; shared curator unchanged.')
