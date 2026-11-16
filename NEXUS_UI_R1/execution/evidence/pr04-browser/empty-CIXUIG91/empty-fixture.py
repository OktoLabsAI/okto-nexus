"""Canonical empty workspace plus existing-connection scope, own fixture only."""
import importlib.util
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ui04_empty_parent',HERE/'fixture.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original=base.seed


def seed(s):
    ids=original(s)
    with s.factory.unit_of_work() as uow:
        s.deps.repos.workspaces.upsert(uow,workspace_id='ui04-empty')
        uow.connection.execute("UPDATE workspaces SET display_name='Empty qualified project' WHERE workspace_id='ui04-empty'")
    return dict(ids,empty_workspace='ui04-empty',existing_workspace='ws')


base.seed=seed
if __name__=='__main__':base.main()
