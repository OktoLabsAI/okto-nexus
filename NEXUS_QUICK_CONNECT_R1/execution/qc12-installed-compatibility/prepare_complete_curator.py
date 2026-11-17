"""Derive final curation without overwriting the eight-case antecedent."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
text = (HERE / 'curate_git_final.py').read_text()
text = text.replace("HERE / 'git-final-allocation.json'", "HERE / 'git-complete-allocation.json'")
text = text.replace("HERE / 'git-final-evidence'", "HERE / 'git-complete-evidence'")
text = text.replace("    shutil.copyfile(ROOT / name, OUT / name)", "    if (ROOT / name).exists():\n        shutil.copyfile(ROOT / name, OUT / name)", 1)
text = text.replace("'No repository source/tests, installed prefix, personal environment or earlier evidence changed.'",
    "'D25 is limited to the initial canonical stdout privacy assertions; persistence, resume JSON privacy and telemetry were not asserted in this composed cut.',\n        'No repository source/tests, installed prefix, personal environment or earlier evidence changed.'")
text = text.replace("antecedents='git-integration-evidence preserves original interrupted byte-oracle run and strict one-path derivative FAIL; neither is relabeled green.'",
    "antecedents='git-integration-evidence preserves original interrupted byte-oracle run and strict one-path derivative FAIL; git-final-evidence retains the eight-case run whose curation rejected the missing two fallback cases. None is relabeled as this final ten-case result.'")
text = text.replace("('run_git_final.py', 'prepare_git_final_oracle.py', 'curate_git_final.py')",
    "('run_git_complete.py', 'prepare_git_complete.py', 'curate_git_complete.py')")
(HERE / 'curate_git_complete.py').write_text(text, encoding='utf-8')
