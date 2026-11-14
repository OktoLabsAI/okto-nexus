from pathlib import Path
source=Path(__file__).with_name('qualify_affected.py').read_text()
source=source.replace("Q=S/'affected-001'", "Q=S/'affected-final'")
source=source.replace("str(S/'test_lifecycle_cleanup.py'),'--basetemp'", "str(S/'test_lifecycle_cleanup.py'),str(S/'test_control_adoption.py'),'--basetemp'")
source=source.replace("S/'test_lifecycle_cleanup.py']}","S/'test_lifecycle_cleanup.py',S/'test_control_adoption.py']}")
exec(compile(source,__file__,'exec'))
