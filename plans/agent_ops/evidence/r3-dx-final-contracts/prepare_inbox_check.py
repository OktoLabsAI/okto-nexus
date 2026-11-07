from pathlib import Path
root=Path('C:/Users/jpamb/AppData/Local/Temp/r3-cooperative-drain-09ucmgsr')
s=(root/'qualify_nexus.py').read_text(encoding='utf-8')
start=s.index('selected=')
end=s.index('\nproof={}',start)
s=s[:start]+"selected=['tests/execution_r4/test_session_read_tools.py::test_another_agent_inbox_is_denied']"+s[end:]
s=s.replace("out=root/'nexus-installed-v1'","out=root/'nexus-inbox-scope'")
(root/'qualify_inbox.py').write_text(s,encoding='utf-8')
