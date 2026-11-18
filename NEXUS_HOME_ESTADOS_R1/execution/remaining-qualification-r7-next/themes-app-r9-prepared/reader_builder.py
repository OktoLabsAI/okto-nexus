"""Own fixture-only SQL read fault. No DTO, authority or persistent-data mutation."""
import hashlib
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent/'experience-batch/builder.py'

def build(root,*,naming_only=False):
    assert not naming_only
    spec=importlib.util.spec_from_file_location('qualified_theme_fixture',SOURCE)
    base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
    report=base.build(root,naming_only=False)
    path=root/'fixture.py';text=path.read_text()
    old="'exp-terminal-a1']:"
    new="'exp-terminal-a1','theme-facts-fail','theme-facts-restore']:"
    assert text.count(old)==1;text=text.replace(old,new)
    controls='''
                    if name=='theme-facts-fail':
                        from okto_nexus.adapters.outbound.sqlite import home_operational_facts as theme_facts
                        import sqlite3
                        query=app.state.home_entries.queries
                        exp['theme_rows_original']=query._rows
                        def fail_operational_rows(uow,sql,params,check_budget=None):
                            if sql==theme_facts.SESSIONS:
                                raise sqlite3.OperationalError('Own fixture operational fact reader unavailable')
                            return exp['theme_rows_original'](uow,sql,params,check_budget)
                        patch.setattr(query,'_rows',fail_operational_rows)
                        exp_snapshot('theme-unknown')
                    if name=='theme-facts-restore':
                        patch.setattr(app.state.home_entries.queries,'_rows',exp.pop('theme_rows_original'))
                        exp_snapshot('theme-restored')
'''
    anchor="                    done.add(name);write('controls.json',dict(done=sorted(done)))"
    assert text.count(anchor)==1;text=text.replace(anchor,controls+anchor)
    path.write_text(text)
    report.update(derivative_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fault='Only installed SQLiteHomeEntryRelations instance _rows when SQL equals installed home_operational_facts.SESSIONS; restore original callable',authority_mutations=False,synthetic_outcome_unknown=False)
    return report
