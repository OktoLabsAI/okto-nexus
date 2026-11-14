from pathlib import Path
source=Path(__file__).with_name('qualify_affected.py').read_text()
source=source.replace("Q=S/'affected-001'","Q=S/'affected-wrapper-fix'")
source=source.replace("raise SystemExit(pytest.main(['-q'", "tests=[str(D/'controller/test_work_wrapper.py'),str(D/'controller/test_v14_delta.py')+'::test_two_decisions_recover_each_exact_saved_checkpoint']\nraise SystemExit(pytest.main(['-q'")
source=source.replace('Affected v14 delta:','Final wrapper shadowed cadence variable fix only; rerun whole wrapper plus multi-decision recovery. Other affected32 passes remain qualified against identical sources. Earlier v14 delta:')
exec(compile(source,__file__,'exec'))
