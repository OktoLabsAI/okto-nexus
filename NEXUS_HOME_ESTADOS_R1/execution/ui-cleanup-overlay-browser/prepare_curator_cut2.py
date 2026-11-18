"""Create a cut2-only curator without modifying the preserved first cut."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
text=(HERE/'curate.py').read_text().replace("HERE/'runtime.json'","HERE/'runtime-cut2.json'").replace("HERE/'cut-1'","HERE/'cut-2'")
text=text.replace("'command-focal.private.txt'","'command-focal.private.txt','overlay-home.png','overlay-terminal.png'")
text=text.replace("status='FAIL_PRESENTATION_GENERIC_RESULT_EVENT_TITLE_FIRST_FAILURE_PRESERVED'","status='PASS_PRESENTATION_OVERLAY_CANONICAL_CLOSE_UNKNOWN'if final['unknown']else'PASS_PRESENTATION_OVERLAY'")
text=text.replace("runtime_exit=1","runtime_exit=0")
text=text.replace("failure=result['error']","failure=result.get('error')")
text=text.replace("qualified=['Real Chrome loaded exact index-Cp1x7DiS.js static overlay','Home no Connection details or Evidence observed']","qualified=[c['id']for c in result['checks']if c['pass']]")
text=text.replace("not_qualified=['Local timestamp/datetime rendering','View work exact target/session terminal','No IDs outside disclosure','READY/control command and Copy command affordance']","not_qualified=['Actual clipboard copy; button was not clicked','New SQL subject projection and new installed package; runtime API remains old R9']")
text=text.replace("cause_evidence='Captured AX shows idle card Activity preview paragraph Work request, Turn completed, View delivery; result-kind event retains generic title.'","cause_evidence='No failure; all13 scoped presentation assertions passed'")
text=text.replace("browser_writes=result['writes'],page_errors=result['pageErrors']","browser_writes=next(c['actual']for c in result['checks']if c['id']=='zero-browser-POST'),page_errors=next(c['actual']for c in result['checks']if c['id']=='zero-page-errors')")
start=text.index("(out/'README.md').write_text(");end=text.index('\nmanifest=',start)
text=text[:start]+'''(out/'README.md').write_text("""# 8q overlay focal —13/13 positive

Real Chrome + unchanged installed R9 HTTP API + new Vite static-only overlay. This is not a newly installed package. The frozen prefix1031 payload and all original backend checkout bytes were checked except exactly sqlite/home.py, whose explicit new SHA is bound separately; the runtime still imports old R9 home.py. New SQL subject projection requires its separate SQLite/pytest evidence.

Home generic Work request/Connection details/Evidence observed were absent. Received timestamp retained its raw datetime while rendering browser-local Sao Paulo text. Exact View work opened the canonical target with GET200/full12-field session scope, visible real Turn started output, technical IDs hidden in basic view, READY/control_available true/no release pending. The terminal disclosure contained the exact existing-session command and enabled Copy command affordance. Copy was not clicked: no proven isolated browser clipboard, Windows clipboard untouched. No browser POST/page errors/provider calls.

Runner/CLI/fixture normal0; no signals or forced containment. All observed own process births/profile/listener absent. Canonical B1 close confirmed, A1/A2 UNKNOWN remains separate. Public screenshots were viewed and contain synthetic fixture UI only, with terminal command disclosure closed. No human acceptance, real provider or new installed-package qualification.
""")''' +text[end:]
(HERE/'curate_cut2.py').write_text(text)
