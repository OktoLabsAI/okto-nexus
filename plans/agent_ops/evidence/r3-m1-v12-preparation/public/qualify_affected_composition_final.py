from pathlib import Path
source=Path(__file__).with_name('qualify_affected_composition.py').read_text()
source=source.replace("Q=R/'affected-composition'", "Q=R/'affected-composition-final'")
exec(compile(source,__file__,'exec'))
