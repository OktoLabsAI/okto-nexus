"""Curate current scope without relabelling immutable historical cut outcomes."""
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
def main():
    rollup=json.loads((HERE/'qualification.json').read_text(encoding='utf-8'))
    extra={
        'r5-working-draft-terminal':['28 positive checks: actual Working, independently blocked request, dirty two polls, one canonical answer, confirmation and later exact terminal/output/delivery in same panel','No denial/lost-response/two-tab decision claim'],
        'r5-info-upgrade-antecedent':['Retained failing predecessor; info negotiation remounts dirty form'],
        'r5-info-upgrade-observables':['Exact old-node disconnect/value/focus loss established; fixed and qualified separately on R6'],
        'r5-scope-observer-antecedent':['First transport observer insufficient; B correct before A release; not a product failure'],
        'r5-scope-response-abandoned':['A headers200 delivered after B200; unchanged forwarded bytes SHA matched; requestfinished/body completion not observed because abandoned fetch','Five positive checks; late-response whole journey remains incomplete, not a forced PASS'],
        'r5-failed-cancelled':['Actual inert protocol failed/cancelled canonical terminals and semantics; cleanup-pending-success branch not run'],
        'r6-info-draft-focus':['Same DOM node/value/focus retained across delayed real info; version1 until context closed and board focus blurred; then2; zero POST'],
        'r6-manual-pause-auth':['Manual pause retains1 after info; real own-session logout401 clears Home','V1 protected-card precondition selector used v2 attribute and failed; preserved oracle limitation, not whole journey PASS'],
        'r6-final-working-intents':['Final R6 canonical current Working plus independent operator question; labels Chat/Ask for work, keyboard open/close/focus and mobile360 subset','No actual composer send/payload integration claim; no full keyboard/AT claim']}
    existing={x['cut']for x in rollup['scopes']}
    for tag,limits in extra.items():
        path=HERE/'cuts'/tag/'qualification.json'
        if not path.exists():continue
        q=json.loads(path.read_text(encoding='utf-8'))
        assert not q['cleanup']['own_root_processes']and not q['cleanup']['listener_pids']
        name='cuts/'+tag
        if name not in existing:rollup['scopes'].append(dict(cut=name,status=q['status'],checks_pass=q['checks_pass'],checks_fail=q['checks_fail'],limits=limits))
    rollup.update(status='R6_FUNCTIONAL_SUBSETS_COMPLETE_WITH_EXPLICIT_GAPS',active_resources=False,package_ready=dict(r3=True,r4=True,r5=True,r6=True),
        current_blockers=['Large-dataset500ms performance target remains separately unqualified; no waiver','Whole J1-J8 matrix is not qualified from these subsets; human and AT not run'],
        remaining_browser_scope=['J1three native families NOT_RUN; synthetic Codex protocol only','J4 denial/lost-response/two-tab CAS NOT_RUN','J6 cleanup-pending terminal variant NOT_RUN; failed/cancelled subset PASS','J7 A→B late-response transport completion incomplete, despite A headers after B and intact forwarded hash; real logout/source partial subsets PASS','Full browser history/back-forward, complete keyboard traversal and project-switch dirty guard not qualified','G08 labels/selection and stable canonical test IDs qualified; actual composer send not run','Native200percentzoom and actual screen-reader AT NOT_RUN'],
        final_source_commit='90b94ca9673c087554b7dc4a226490ef5417bd32',no_global_slo_claim=True)
    (HERE/'qualification.json').write_text(json.dumps(rollup,indent=2)+'\n',encoding='utf-8')
    dest=HERE/'screenshots-r5-r6';dest.mkdir(exist_ok=True)
    names=['r5-same-panel-output.png','r5-negative.png','r6-info-draft.png','r6-final-mobile.png']
    entries=[]
    for name in names:
        src=HERE.parents[2]/'output/playwright/home-states'/name
        if not src.exists():continue
        out=dest/name
        if out.exists():assert out.read_bytes()==src.read_bytes()
        else:shutil.copyfile(src,out)
        entries.append(dict(path=name,sha256=hashlib.sha256(out.read_bytes()).hexdigest(),bytes=out.stat().st_size))
    (dest/'manifest.json').write_text(json.dumps(entries,indent=2)+'\n')
    print(json.dumps(dict(scopes=len(rollup['scopes']),screenshots=len(entries),active_resources=False)))

if __name__=='__main__':main()
