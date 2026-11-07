import collections, hashlib, json, pathlib, re

root = pathlib.Path(r'D:/Projetos/Techridy/okto_labs_okto_nexus')
out = root / 'output/playwright/dx04-participant-guide'
records = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in out.glob('[0-9][0-9]-*.json')}
def result(name):
    text = records[name]['stdout'].split('### Result\n', 1)[1].split('\n### Ran', 1)[0].strip()
    return json.loads(text)
checks = []
def check(name, passed, evidence, detail):
    assert passed, name
    checks.append(dict(name=name, status='PASS', evidence=evidence, detail=detail))

a=result('10-public-command-dom')
check('existing_identity_readonly',a['inputs'][0] == {'value':'dx04-agent-alpha','readOnly':True},['10-public-command-dom.json'],'Agent action binds the selected identity without key access.')
check('all_workspaces_requires_input',result('04-all-empty-assert')['commands']==0,['03-existing-all-snapshot.json','04-all-empty-assert.json'],'No workspace inferred from All workspaces; the later input receives six public commands.')
check('public_claude_steps',len(a['commands'])==6 and '--client=claude' in a['commands'][0],['10-public-command-dom.json'],'Init review/apply, foreground launch review/apply and passive/explicit MCP doctor are distinct.')
check('no_browser_approval_gate',result('04-all-empty-assert')['checkboxes']==0 and result('26-generic-command-scope')['checkboxes']==0,['04-all-empty-assert.json','26-generic-command-scope.json'],'Valid fields generate commands immediately; CLI review remains explicit.')
check('desktop_dialog_focus_and_width',a['focusInsideDialog'] and a['viewport']==a['body'],['10-public-command-dom.json','desktop-claude.png'],'Native dialog is in viewport and contains active focus.')
check('clipboard_success','Public command copied.' in result('12-copy-success')['status'][0],['11-copy-public-command.json','12-copy-success.json'],'Actual browser clipboard write succeeded; no clipboard contents read.')
check('clipboard_refusal','Clipboard unavailable.' in result('19-copy-failure-status')['status'][0],['17-clipboard-failure-injection.json','18-copy-refused.json','19-copy-failure-status.json','20-restore-clipboard.json'],'writeText rejection was explicitly injected and restored; UI offers manual copy.')
snap=records['15-codex-https-snapshot']['stdout']
check('codex_https_port_preserved',"--server='https://nexus.example.test:9443'" in snap and '--client=codex' in snap,['15-codex-https-snapshot.json'],'Public origin input only; no HTTPS network request or TLS qualification.')
invalid=result('22-invalid-origin-refusal')
check('remote_http_refused',invalid['commands']==0 and 'HTTPS Server origin' in invalid['status'][0],['21-invalid-remote-http.json','22-invalid-origin-refusal.json'],'Invalid remote plaintext origin yields no commands.')
generic=result('26-generic-command-scope')['commands']
check('generic_has_no_launch',len(generic)==4 and '--client=generic' in generic[0] and all('participant launch' not in c for c in generic),['25-generic-snapshot.json','26-generic-command-scope.json'],'Generic manual guidance is explicitly unqualified and has no launch command.')
focus=result('28-focus-restored')
check('escape_restores_trigger',focus['dialogs']==0 and focus['focusLabel']=='Existing client for dx04-agent-alpha',['27-close-escape.json','28-focus-restored.json'],'Escape closes edited public guide without a discard confirmation and restores the agent trigger.')
prefill=result('33-selected-workspace-prefill')
check('selected_workspace_prefilled',prefill['inputs'][1]['value']=='dx04-workspace-alpha' and prefill['commands']==6,['30-select-workspace.json','33-selected-workspace-prefill.json'],'Selected workspace and origin populate a new guide.')
mobile=result('36-mobile-layout')
check('existing_mobile_layout',mobile['viewport']==mobile['body']==390 and all(x['width']==x['scroll'] for x in mobile['overflows']),['35-mobile-snapshot.json','36-mobile-layout.json','mobile-existing.png'],'390x844 viewport, inputs/selects/commands without horizontal overflow; screenshot visually inspected.')
check('mobile_keyboard_focus',result('41-mobile-focus')['focusInside'],['40-mobile-tab.json','41-mobile-focus.json'],'Tab enters the visible native-dialog close control after viewport resizing.')
check('empty_server_onboarding', 'Use your existing MCP client' in records['46-onboarding-existing-snapshot']['stdout'] and 'Enter the existing agent ID and workspace ID' in records['46-onboarding-existing-snapshot']['stdout'],['44-onboarding-snapshot.json','46-onboarding-existing-snapshot.json'],'Only reserved operator exists; guidance does not provision missing identities. Later external-agent/external-workspace are illustrative input, not authenticated identities.')
check('onboarding_keyboard_wrap',result('50-onboarding-focus')=={'label':'Open Agents','inside':True},['49-onboarding-keyboard-wrap.json','50-onboarding-focus.json'],'Shift+Tab from first header control wraps to last footer control.')
dark=result('56-onboarding-dom')
check('onboarding_dark_mobile',dark['dark'] and dark['viewport']==dark['body']==390 and dark['horizontalOverflows']==0 and len(dark['commands'])==6,['53-onboarding-posix.json','56-onboarding-dom.json','mobile-onboarding-dark.png'],'Bash/zsh selected, dark390x844 layout without horizontal overflow; screenshot visually inspected.')
network={}
for label,name in [('agents','38-existing-requests'),('onboarding','58-onboarding-requests')]:
    requests=re.findall(r'^\d+\. \[([A-Z]+)\] (\S+)',records[name]['stdout'],re.M)
    assert requests
    methods=dict(collections.Counter(m for m,u in requests))
    check(label+'_network_read_only',set(methods)=={'GET'},[name+'.json'],'Captured browser request list contains no POST/PUT/PATCH/DELETE; critical DB hashes supply independent state proof.')
    network[label]=dict(captured_requests=len(requests),methods=methods,scope='current page request list at checkpoint; successful static resources omitted')
for name in ['39-existing-console','59-onboarding-console']:
    check(name,'Total messages: 0 (Errors: 0, Warnings: 0)' in records[name]['stdout'],[name+'.json'],'No console warnings/errors during this page campaign.')
check('browser_closed',records['60-close-browser']['exit_code']==0 and "Browser 'dx04-guide' closed" in records['60-close-browser']['stdout'],['60-close-browser.json'],'Only the named isolated QA browser session was closed.')
for p in out.glob('*'):
    if p.suffix=='.json':
        assert not re.search(rb'nxs_[a-fA-F0-9]{48}',p.read_bytes()),p.name

report=dict(status='VERIFIED_DECLARED_BROWSER_SCOPE',checks=checks,check_count=len(checks),network=network,
            command_records=len(records),command_exit_failures={k:v['exit_code'] for k,v in records.items() if v['exit_code']},
            screenshots_visually_reviewed=['desktop-claude.png','mobile-existing.png','mobile-onboarding-dark.png'],
            failures_and_limits=[
                'Initial Agents click before readiness was intercepted by pre-existing metrics opt-in. Refreshed snapshot and closed metrics via its explicit Close action; no metrics write.',
                '04 initially queried the agent input under the misleading field name workspace and searched explicit role=dialog instead of native dialog; those two fields are not used as evidence. 08 failed on the same native-dialog selector. Corrected observations are in10 and33.',
                '01 and16 custom Node request-monitor attempts yielded no serialized result; they are retained but supply no proof. CLI requests38/58 and DB baselines are authoritative.',
                'Browser shell selections and public strings do not execute init/apply/launch/doctor or test provider login, actual client, TLS, OS vault, native service, M1/M2 or joint R3.',
                'No create/regenerate/Finish control or one-shot key panel was opened; no credential was entered, read from clipboard, or captured.',
                'No product change was needed during browser qualification; wheel remains candidate-v1.'
            ])
(out/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:report[k] for k in ['status','check_count','command_records','command_exit_failures','network']},indent=2))
