"""Prepare own temporary extension/profile/config only; no browser launch."""
from pathlib import Path
import json
import tempfile

ROOT=Path(__file__).resolve().parents[4]
out=ROOT/'output/playwright/ui09-native-zoom'
out.mkdir(parents=True,exist_ok=True)
control=Path(tempfile.mkdtemp(prefix='nexus-ui09-zoom-control-'))
extension=control/'extension';extension.mkdir()
(extension/'manifest.json').write_text(json.dumps(dict(manifest_version=3,name='Own Nexus native zoom qualification',version='1.0',
    host_permissions=['http://127.0.0.1/*'],background=dict(service_worker='worker.js'))),encoding='utf-8')
(extension/'worker.js').write_text("chrome.runtime.onInstalled.addListener(()=>console.log('OWN_ZOOM_EXTENSION_READY'));\n",encoding='utf-8')
browser=Path('C:/Users/jpamb/AppData/Local/ms-playwright/chromium-1254/chrome-win64/chrome.exe')
config=dict(browser=dict(browserName='chromium',isolated=False,userDataDir=str(control/'profile'),
    launchOptions=dict(executablePath=str(browser),channel='chromium',headless=True,
        args=[f'--disable-extensions-except={extension}',f'--load-extension={extension}','--window-size=1440,1100']),
    contextOptions=dict(viewport=None)),outputDir=str(out),outputMode='stdout')
(control/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
(out/'control.json').write_text(json.dumps(dict(control=str(control),extension=str(extension),profile=str(control/'profile'),browser=str(browser)),indent=2),encoding='utf-8')
print(control)
