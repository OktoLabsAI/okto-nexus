import pytest

@pytest.fixture(autouse=True)
def no_real_provider_or_credentials(monkeypatch):
    import subprocess,win32cred
    class NoProcess(subprocess.Popen):
        def __init__(self,*args,**kwargs):raise AssertionError('Native/subprocess forbidden in drain regression')
    def deny(*args,**kwargs):raise AssertionError('Credential store forbidden in drain regression')
    monkeypatch.setattr(subprocess,'Popen',NoProcess)
    for name in ('CredRead','CredWrite','CredDelete','CredEnumerate'):monkeypatch.setattr(win32cred,name,deny)
