"""Apply explicit, bounded QC judgments; keep the normative ledger immutable."""
from collections import Counter
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / 'NEXUS_QUICK_CONNECT_R1'
OLD = 'a0fa79129d8760eef945fc1445c2355430d5b54c'
CURRENT = 'fa031697b37a1b879d855f7858f01320addf0df7'
FINAL_CANCELLATION_QUALIFIED = False
FINAL_SHELL_RENDER_QUALIFIED = False

# These are literal scenario decisions, not an inference from file membership.
LATER = [
    (['QC-T-A14'], 'execution/qc12-installed-compatibility/qualification.json',
     'All three original legacy catalog/multi-harness nodes pass in the rebuilt installed candidate. The original broader cut retains its separate runner failures.'),
    (['QC-T-D01', 'QC-T-D02', 'QC-T-D03', 'QC-T-D04', 'QC-T-D05', 'QC-T-D06',
      'QC-T-D15', 'QC-T-D18', 'QC-T-F19'],
     'execution/qc12-installed-compatibility/git-complete-evidence/qualification.json',
     'Ten composed real-local-Git/installed-CLI/HTTP/SQLite cases: origin formats, fallback review, one final scripted confirmation, monorepo root preservation and completed exact resume after origin changes. Native Test/version peers are synthetic; no real PTY/provider or privacy-telemetry audit.'),
    (['QC-T-E03', 'QC-T-H06', 'QC-T-G13', 'QC-T-F17'],
     'execution/qc14-extra-scenarios/qualification.json',
     'Four initial passing cases plus separate exact project-CAS F17 counterparts: automatic codex-2, both plan namespaces unchanged, expired-grant reuse without renewal, and stale-review refusal before another Test/Finish. Original failing F17 oracle remains an antecedent; this is not one final five-pass run.'),
    (['QC-T-D26'], 'execution/qc14b-autoid-race/qualification.json',
     'Actual own Git origin/branch mutation after lost Finish, then exact pending-intent recovery with discovery forbidden; explicit frozen name, same original request/root/ID/full reference and no Test/grant replay.'),
    (['QC-T-G02'], 'execution/qc14b-autoid-race/qualification.json',
     'Two automatic-add reviews propose the same available suffix; deterministic winner/loser interleaving refuses the stale approval. A separately explicit new intent rereads the occupied namespace, proposes codex-3, refuses the old hash and needs its own approval. This is controlled interleaving, not simultaneous OS processes.'),
    (['QC-T-A03', 'QC-T-B03', 'QC-T-B05', 'QC-T-B06', 'QC-T-B08', 'QC-T-B09'],
     'execution/qc15-cli-choice-scenarios/qualification.json',
     'Eight installed CLI/HTTP cases: literal bare entry and explicit two-family choice/cancel/JSON, stale canonical publication, exact second candidate, shell-like token refusal and case normalization. Choosing Claude reaches the genuine provider-home-required fence; no complete Claude onboarding or real PTY is claimed.'),
    (['QC-T-B07'], 'execution/qc15-cli-choice-scenarios/policy-qualification.json',
     'Canonical persisted METHOD_DISABLED policy produces FRESH inventory with can_configure=false; CLI refuses before probes/Test/profile creation. All 162 tables remain equal after the denied-policy baseline and its canonical revision materialization.'),
    (['QC-T-F03', 'QC-T-F04', 'QC-T-F05', 'QC-T-F06', 'QC-T-F07', 'QC-T-F08',
      'QC-T-F11', 'QC-T-F12', 'QC-T-F23', 'QC-T-E11', 'QC-T-E12', 'QC-T-E17'],
     'execution/qc16-id-choice-scenarios/qualification.json',
     'Nine installed scripted-TTY/JSON HTTP scenarios: same/cross-family explicit reuse, manual ID/suggestion with reviewed new intent, truthful cancel, add cannot resume, pending-other-intent and exact-selector fences. Original probe-count oracle failure remains separate; installation-ready state can avoid another version probe.'),
    (['QC-T-C01', 'QC-T-C03', 'QC-T-C04', 'QC-T-C09', 'QC-T-C10', 'QC-T-C11',
      'QC-T-C17', 'QC-T-E04'], 'execution/qc17-project-choice-scenarios/qualification.json',
     'Six installed project/root cases across declared cuts: true bare and harness resume, labels separate from directories, explicit root choice/JSON refusal, and cancel/approve never mkdir a logical label. Controlled TTY input, not a human or real PTY; original fixture/plan-envelope oracle failures retained.'),
    (['QC-T-F21', 'QC-T-H01'], 'execution/qc18-customization-output/qualification.json',
     'Installed CLI customizes name/harness/root with fresh intent/hash/reservation and superseded old approval, preserving invocation A versus selected B. Together with the earlier ID customization this covers four fields. Real output is inspected before the inert chat callback; no project work is launched.'),
    (['QC-T-F15', 'QC-T-F16'], 'execution/qc19-pending-selector-fences/qualification.json',
     'Three lost-Finish selector contradictions preserve pending bytes and all authority; exact recovery uses original receipt without replay. Genuine nonoperator agent-key HTTP requests are denied without occupant/private-ref disclosure; operators retain global namespace access, not invented workspace ACL.'),
    (['QC-T-D08', 'QC-T-D09', 'QC-T-D11', 'QC-T-D12', 'QC-T-D13', 'QC-T-D14',
      'QC-T-D21', 'QC-T-D22'], 'execution/qc20-git-boundary-scenarios/qualification.json',
     'Eight composed installed CLI/local-Git cases: missing Git/nonrepo/invalid origin fallbacks, actual linked worktree/worktree config/nested repo, poisoned Git env and rejected fake CWD Git. The fake binary is a Popen marker tripwire, not an executed malicious PE; no Git network/global config change.'),
    (['QC-T-C05', 'QC-T-C06', 'QC-T-C07', 'QC-T-C08', 'QC-T-C16'],
     'execution/qc23-project-directory-scenarios/qualification.json',
     'Five installed canonical-directory cases: duplicate labels require choice, exact workspace ID wins, mismatched name/ID refuses, explicit root B survives Finish/resume, and a target beyond page one in 105 workspaces uses stable cursor/revision/exact total before Test.'),
    (['QC-T-F20'], 'execution/qc21-review-privacy/qualification.json',
     'Two focal assertions passed: actual monorepo review is inspected before y for name/source/CWD/root/host/adapter/ID/every effect; private-origin checkpoint/table/JSON surfaces are checked. Initial Windows process crash and a post-pytest cleanup-race assertion remain failures; independent final process/payload/pin checks are recorded. Not a universally green runner or telemetry audit.'),
    (['QC-T-G09'], 'execution/qc22-owned-console-interrupt/qualification.json',
     'Original unmodified test passed with real CONIN$/GetConsoleMode input in an owned hidden Windows console. One Ctrl-C only after issued marker and fresh console ownership fence: CLI130, checkpoint retained, no binding/grant, explicit fixture gate release, all owned clients/conhosts exited. No user/RTK console signal.'),
    (['QC-T-E06', 'QC-T-E07', 'QC-T-E09'], 'execution/qc24-namespace-scenarios/qualification.json',
     'Three new installed HTTP/SQLite scenarios: uppercase/lowercase ID collision, two separately Finished project namespaces, and a canonically registered second executor cannot claim an occupied workspace ID. No real remote transport/host/harness is asserted.'),
    (['QC-T-E08'], 'execution/qc24-namespace-scenarios/qualification.json',
     'Assertion review of the already executed installed predecessor node: two actual homes/factories/SQLite databases and distinct installation ServerIDs reserve the same textual workspace/ID independently. No new a36 execution or separate OS daemon is asserted.'),
    (['QC-T-F24'], 'execution/qc25-git-home-continuity/qualification.json',
     'Real installed Server and own browser reopen the original Git fixture home after origin mutation: same logical project, public ID and exact binding target. 126GET/0POST, protected tables unchanged, sessions/operations remain zero. Preserved STALE/partial status is not execution readiness or multisession qualification.'),
    (['QC-T-C18', 'QC-T-G12', 'QC-T-G15'], 'execution/qc25-concurrency-locks/qualification.json',
     'Two exact approved first-connection reviews reach a real POST-reserve barrier: one Test/Finish and one canonical draft/workspace/ID/binding/grant/receipt. Separate process-lock probes demonstrate busy refusal, recovery, global catalog lock free during input and old profile released before the new review. A separately authorized inert installation check establishes the READY fixture precondition.'),
    (['QC-T-C12', 'QC-T-C14', 'QC-T-F13', 'QC-T-H09'],
     'execution/qc27-local-edge-scenarios/qualification.json',
     'Four installed focals: removed captured-CWD fault gives generic structured CONFIG_ERROR before resolver/no HOME fallback; actual own Windows junction retarget invalidates old approval; canonical endpoint disable retains occupied ID without reactivation/connected; shell=False Python argv roundtrip preserves Unicode/spaces/metacharacters without executing them. Not removal of a live Windows CWD or a shell renderer.'),
    (['QC-T-I05'], 'execution/qc29-participant-regression/qualification.json',
     'Twenty-five byte-unchanged installed legacy participant nodes pass: init/connect dispatch, configuration/credential-reference preservation and selected launch/replay. MemoryVault/HTTPBridge and spawn fakes are explicit; no personal credential backend or real Codex/Claude was used.'),
    (['QC-T-D17'], 'execution/qc14b-autoid-race/qualification.json',
     'Explicit frozen name wins in an actual owned Git repository with a different origin. Plan/application/recovery keep the explicit name; discovery is forbidden during pending recovery and existing fixture guards forbid unapproved Git work.'),
    (['QC-T-G04', 'QC-T-H10'], 'execution/qc16-id-choice-scenarios/qualification.json',
     'A canonical reserved-only other intent prints a nonconnected pending refusal; cancel returns0 with canceled state and truthful lifecycle metadata, while existing JSON plan evidence stays planned. Exit code alone is never used as connection proof.'),
    (['QC-T-G11'], 'execution/qc18-customization-output/qualification.json',
     'Together with the earlier actual ID customization, changed ID/root/name/harness get new review hashes and intents; stale approvals are refused before another effect. Original requests remain preserved.'),
    (['QC-T-F22'], 'execution/qc05-browser/qualification.json',
     'Actual English Home/selector screenshots show Harness ID, while installed CLI evidence uses ID do Harness with the same connect_id meaning. No new menu/global translation or human-usability acceptance is inferred.'),
    (['QC-T-I01'], 'execution/qc12-installed-compatibility/qualification.json',
     'Current installed original legacy --client/--project/--profile catalog/multi-harness nodes pass; the fixed legacy request hash and receipt omission have their earlier independent installed golden evidence. This is not a claim that the broader regression is green.'),
    (['QC-T-I07'], 'execution/qc21-review-privacy/qualification.json',
     'Private-origin output/checkpoints and resume JSON remain sanitized; earlier installed unsafe-provenance/private-extension allowlist tests preserve disk members without echo. Bounded hostile inputs/surfaces only; no claim of universal telemetry auditing.'),
    (['QC-T-C15'], 'execution/qc28-posix-paths/qualification.json',
     'Actual Windows path/junction evidence is complemented by 202 isolated installed Ubuntu WSL2/Python3.13.1 checks. POSIX filesystem cases prove Repo/repo distinct inodes, symlink physical identity and literal backslash versus separator. WSL is not native Ubuntu CI or an untested OS/Python matrix.'),
    (['QC-T-I03'], 'execution/qc30-remote-public-id/qualification.json',
     'Installed main resolves a canonically associated ID through an authenticated remote operator profile, preserving exact seven-field reference/configuration and ignoring local CWD/Git. After association only 23GET and 12 tables unchanged; Server-embedded viewed remotely, not two physical machines.'),
    (['QC-T-G14'], 'execution/qc33-shared-service/qualification.json',
     'A real foreground Server PID/ServeLock/HTTP listener and production readiness/resolver are correlated across five observations. Two explicit connection confirmations preserve instance/generation and the first profile/config/grant; Popen is forbidden with zero attempts. Version/model Test peers are synthetic; Windows Scheduler/relogin or a real provider are not qualified.'),
    (['QC-T-D07', 'QC-T-D10', 'QC-T-D16', 'QC-T-D19', 'QC-T-D20', 'QC-T-D23', 'QC-T-D24'],
     'execution/qc32-git-remaining/qualification.json',
     'Eight unique scenarios across declared cuts: origin wins, controlled reader timeout/invalid output fallback, real same-name clone namespaces, explicit B origin despite CWD A, controlled ownership refusal without override, Git-free help/plan and actual bare-directory fallback. Reader faults are injected; actual bounded subprocess behavior has its separate adapter evidence. Original help spelling/selection errors retained.'),
    (['QC-T-C13'], 'execution/qc34-ancestor-privacy/qualification.json',
     'Actual Nexus-registered ancestor precedes the subdirectory invocation. Finite explicit new-project choice and final approval keep the child root, with the original parent profile/binding/grant untouched. The earlier Git-only monorepo was insufficient and remains separate.'),
    (['QC-T-D25'], 'execution/qc34-ancestor-privacy/final-private-focal/qualification.json',
     'Live final focal: enabled DEBUG sink with before/after markers and 75 HTTPX records, four JSON surfaces, 18 files fully read and live SQL163tables/602text cells show no private input. Only exact immutable one-byte journal mutex is proved by stable identity/size/owner descriptor/producer hash and length<all private markers, then read NUL after close. Earlier access violation and live PermissionError remain failures, not retrospectively attributed or relabeled.'),
    (['QC-T-I06'], 'execution/qc31-multisession-browser/qualification.json',
     'Real browser sees one public ID/full seven-field connection and two canonically admitted distinct sessions: closed retained A and ready B, valid frames/watermarks, exact targets/viewers and exclusive histories. Fifteen checks, 86GET/0POST and no page errors; fixture protocol/Test are synthetic, not provider/AT/human qualification. Peer exit1 values remain literal in cleanup.'),
]


def evidence(path, scope, commit=CURRENT):
    assert (BASE / path).is_file(), path
    return dict(path=path, scope=scope, commit=commit)


def add_evidence(row, item):
    if item not in row['evidence']:
        row['evidence'].append(item)


def main():
    target = BASE / 'NEXUS_QUICK_CONNECT_LEDGER_R1.json'
    ledger = json.loads(target.read_text('utf-8'))
    review = json.loads((BASE / 'execution/coverage-review.json').read_text('utf-8'))
    prior = {row['id']: row for row in review['tests']}
    judgments = json.loads((BASE / 'execution/scenario-reconciliation.json').read_text('utf-8'))
    tests = {row['id']: row for row in ledger['tests']}
    assert len(tests) == len(judgments['rows']) == 147
    for row in judgments['rows']:
        original = prior[row['id']]
        status = row['proposed']
        scope = row['reason'] if row['changed'] else original.get('pass_scope') or original['remaining_acceptance']
        test = tests[row['id']]
        test['status'] = 'PASS' if status == 'PASS' else 'BLOCKED' if status == 'BLOCKED' else 'NOT_RUN'
        test['execution_notes'] = status + ': ' + scope
        test['evidence'] = [evidence('execution/scenario-reconciliation.json',
            'Exact per-scenario judgment, assertions, XML nodes and provenance. ' + scope,
            CURRENT if row['id'] == 'QC-T-I02' else OLD)]
    for ids, path, scope in LATER:
        for identity in ids:
            test = tests[identity]
            test['status'] = 'PASS'
            test['execution_notes'] = 'PASS within the declared boundary: ' + scope
            test['evidence'].append(evidence(path, scope))
    if not FINAL_SHELL_RENDER_QUALIFIED:
        tests['QC-T-H09']['status'] = 'NOT_RUN'
        tests['QC-T-H09']['execution_notes'] = (
            'PARTIAL: QC27 proves the unexecuted argv array and shell=False roundtrip, '
            'but not the required per-shell rendering. Final audit found the missing presentation; '
            'implementation and installed shell-rendering qualification are pending.')
    if not FINAL_CANCELLATION_QUALIFIED:
        tests['QC-T-G08']['status'] = 'FAIL'
        tests['QC-T-G08']['execution_notes'] = (
            'FAIL on the current a36 artifact: canceling a new review returns0 without a final canceled/lifecycle document. '
            'QC35 preserves the exact red case and passing external-only derivatives. Acceptance awaits source application and a new installed package.')
        tests['QC-T-G08']['evidence'].append(evidence(
            'execution/qc35-review-cancellation-proposal/revision2/qualification.json',
            'Current installed red versus external connect-only patch; the derivative is not a fixed installed wheel.'))
    tasks = {row['id']: row for row in ledger['tasks']}
    tasks['QC-027']['status'] = 'IMPLEMENTED'
    tasks['QC-022']['status'] = 'IMPLEMENTED' if FINAL_CANCELLATION_QUALIFIED else 'IN_PROGRESS'
    add_evidence(tasks['QC-027'], evidence('execution/qc13-entry-smoke/proof.json',
        'Actual installed old Server unsupported-capability refusal; exact HTTP status preserved. No local namespace substitute/provider.'))
    add_evidence(tasks['QC-028'], evidence('execution/qc12-installed-compatibility/qualification.json',
        'Original legacy CLI nodes pass in the new installed package; unknown fields and hashes retain their independent evidence.'))
    tests['QC-T-I08']['status'] = 'PASS'
    tests['QC-T-I08']['execution_notes'] = ('PASS for the literal installed-entry/dependency/artifact scenario: '
        'QC11/12/13 establish the new isolated package, help/parser/connect and 1027 exact payloads. '
        'The broader regression remains a separate NOT_GREEN qualification gate; this row does not promote it.')
    tests['QC-T-I08']['evidence'].extend([
        evidence('execution/qc11-package/qualification.json', 'Fresh isolated wheel/sdist build, install, smoke, exact payload and dependency gates.'),
        evidence('execution/qc12-installed-compatibility/qualification.json', 'Installed feature and legacy CLI checks with separately preserved runner failures/counterparts.'),
        evidence('execution/qc13-entry-smoke/proof.json', 'Actual installed console cold plan, explicit script guard and old-Server refusal.'),
        evidence('execution/qc09-installed-01/qualification.json', 'Original and derivative broad results, incomplete inventories and frozen input/process proofs.', OLD),
        evidence('execution/qc09-installed-23/qualification.json', 'Full shard3 failure and interrupted shard2 with original evidence/provenance retained.', OLD),
    ])
    for identity in ('QC-029', 'QC-030', 'QC-033'):
        tasks[identity]['status'] = 'IN_PROGRESS'
    tasks['QC-031']['status'] = 'BLOCKED'
    for requirement in ledger['requirements']:
        requirement['status'] = 'PARTIAL'
        requirement['evidence'] = [evidence('execution/scenario-reconciliation.json',
            'Scenario-level evidence and concrete remaining acceptance; implementation is not global qualification.', OLD)]
        requirement['execution_notes'] = 'PARTIAL: scoped automated proofs exist; complete gate not asserted.'
    ledger['execution'].update(candidate=CURRENT,
        implementation_gate='IN_PROGRESS: additional safe composed cases and final reconciliation',
        real_qualification_gate='BLOCKED: fresh real-provider consent and retained UNKNOWN usage guard',
        scenario_status_semantics='PARTIAL uses normative NOT_RUN plus execution_notes; PASS proves only the cited literal boundary.',
        scenario_counts=dict(Counter(row['status'] for row in tests.values())),
        original_broad_gate='NOT_GREEN: failures, hung tests, incomplete remainders and mixed child provenance retained')
    target.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(ledger['execution']['scenario_counts']))


if __name__ == '__main__':
    main()
