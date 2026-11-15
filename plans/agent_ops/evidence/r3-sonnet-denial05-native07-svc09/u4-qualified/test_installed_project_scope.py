"""Actual installed CLI parser/project guard with synthetic profile and no HTTP."""
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import io,json,tempfile,unittest
from okto_nexus.adapters.inbound.cli import work,terminal_target
class Tests(unittest.TestCase):
    def run_case(self,wrong):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);project=home/'campaign';project.mkdir();child=project/'connector-project';child.mkdir()
            profiles=home/'terminal/profiles';profiles.mkdir(parents=True)
            doc={'selection':{'project':str(project.resolve()),'operator_profile':'synthetic'}}
            (profiles/'p.json').write_text(json.dumps(doc))
            calls=[];flow=SimpleNamespace(connection=doc,document={},observe=lambda **kw:(calls.append('GET-only-observe') or {'state':'idle'}))
            target=SimpleNamespace(adapter=SimpleNamespace(home=home),inspect=lambda:{'state':'ready'})
            output=io.StringIO()
            with patch.object(terminal_target,'resolve_terminal_target',return_value=target),patch.object(work,'open_work',return_value=flow),redirect_stdout(output):
                code=work.run_work(['status','--profile','p','--operator-profile','synthetic','--project',str(child if wrong else project),'--home',str(home),'--json'])
            return code,calls,json.loads(output.getvalue())
    def test_saved_project_exact_passes_installed_cli(self):
        code,calls,_=self.run_case(False);self.assertEqual(code,0);self.assertEqual(calls,['GET-only-observe'])
    def test_remote_workspace_is_not_operator_project_and_refuses_before_handler(self):
        code,calls,value=self.run_case(True);self.assertEqual(code,3);self.assertEqual(calls,[]);self.assertEqual(value['code'],'PROFILE_CONFLICT')
if __name__=='__main__':unittest.main(verbosity=2)
