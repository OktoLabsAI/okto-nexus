# Browser-only result and profile contract — read-only follow-up

The single gated diagnostic failed before any phase completed. Open reached its
50s supervisory deadline; no second open/run occurred. Curated qualification:
`../runs/hst-browser-only-direct-node-r8/qualification.json`, SHA
`83fa7754e0e44510847705c257e8d17b497be1a4b7e03737e68e4d93acb93de1`.
No App/Core/Connector module, Server, native peer, npx or npm was used. All pins
remained equal. There were13 observed own process births;11 still-live own
birth/exe-fenced processes required containment, all now absent with0 listeners.
This is FAIL/inconclusive, not normal browser-close PASS or an H01 result.

The new private debug log contains a literal Chrome diagnostic:

> DevTools remote debugging requires a non-default data directory. Specify this using --user-data-dir.

The actual logged launch argv also contains:

```text
--user-data-dir=C:\Users\jpamb\AppData\Local\Temp\nexus-hst-browser-diagnostic-829flnmp\browser-profile
--remote-debugging-pipe
```

The browser was headless. The configured own profile was not absent from the
actual launch argv. Files/directories including Default, Local State and Last
Version exist in that own profile; only their names/metadata were inspected,
not profile contents, cookies or personal browser configuration.

The pinned local CLI implementation proves `--persistent` is **not required**
with `--profile`: resolveCLIConfigForCLI maps options.profile to userDataDir,
makes isolated=false when a profile is supplied, and createBrowser selects
createPersistentBrowser for that mode. The daemon separately sets persistent
when any of options.persistent/options.profile/config.browser.userDataDir is
present. The real argv corroborates that path propagation; adding another flag
is not justified as a fix to a missing profile argument.

Path-only Windows metadata via
`SHGetKnownFolderPath(FOLDERID_LocalAppData,KF_FLAG_DONT_VERIFY)` returned
`C:\Users\jpamb\AppData\Local`, also after LOCALAPPDATA was changed **only in
the metadata process** to the diagnostic's own localappdata and then restored.
No user/system environment setting was changed. The standard Chrome default
derived from that KnownFolder is
`C:\Users\jpamb\AppData\Local\Google\Chrome\User Data`; the default derived
from the sanitized environment would be `OWN_TEMP\localappdata\Google\Chrome\User Data`.
The actual argv user-data-dir is different from **both**. Neither default
directory or personal policy/profile contents were read.

Conclusion: the CLI passed the own Temp profile and Chrome explicitly rejected
the debugging connection as default-directory use. These facts identify the
launch/debugging boundary, but **do not explain Chrome's contradictory default
classification**. No policy, personal-profile fallback, browser incompatibility
or Home/product/performance cause is inferred. No new browser/process run is
authorized by this report, and no personal/CDP fallback is proposed.
