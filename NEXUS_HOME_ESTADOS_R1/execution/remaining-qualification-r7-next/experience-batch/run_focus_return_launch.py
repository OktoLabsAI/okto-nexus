"""Only F07/I02: same allocation/containment, no repeat history/theme/base journeys."""
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent
original=(HERE/'run.py').read_bytes();assert hashlib.sha256(original).hexdigest()=='298bb89a72bf7ea956ede8dd14bd058b82e718b9eae9161028110581a09f6377'
source=original.decode().replace('\r\n','\n');assert source.count("(HERE/'browser.js')")==1
source=source.replace("(HERE/'browser.js')","(HERE/'focus-return.js')")
start=source.index('        # Product AX failure');end=source.index("        (root/'experience-payload.json').write_text",start)
source=source[:start]+"""        assert a.cut=='experience','Only the reviewed minimal focus cut is supported'
        a_card=card(baseline,refs[0]);b_card=card(baseline,refs[1])
        assert a_card['sessions_total']==0 and b_card['sessions_total']==1
        run('initialize',aCard=a_card['id'],bCard=b_card['id'])
        control('exp-start-active');active=read('active');identity=json.loads((root/'control/exp-active-identities.json').read_text())
        actual_a=card(active,refs[0]);assert actual_a['operational_status']['activity']=='working'and actual_a['operational_status']['blocking']=='partial'
        a2=next(s for s in active['sessions']if s['scope']['session_id']==identity['a2']['session_id'])
        requests=[item for item in actual_a['requests_preview']if item['request']['source_id']==identity['question']['request_id']and item['request']['session_id']==identity['a2']['session_id']]
        assert len(requests)==1
        request=requests[0]
        exact=dict(aCard=a_card['id'],bCard=b_card['id'],connection=refs[0],a2Scope=a2['scope'],a2Session=identity['a2']['session_id'],a2Operation=identity['a2']['operation_id'],requestId=identity['question']['request_id'],requestCard=request['id'],attentionId=request['request']['attention_id'],expiresAt=identity['question']['expires_at'],a1Session=identity['a1']['session_id'],a1Operation=identity['a1']['operation_id'])
        run('open',**exact)
        control('exp-terminal-a1');terminal=read('a-terminal');moved=card(terminal,refs[0])
        assert moved['operational_status']['activity']=='waiting_user'and moved['operational_status']['blocking']=='full'and moved['operational_status']['freshness']=='current'
        assert any(item['id']==a_card['id']for item in terminal['board']['columns']['needs_you']['items'])
        deliveries=[item for item in terminal['board']['columns']['results']['items']if item['kind']=='delivery'and item['entry']['target'].get('operation_id')==identity['a1']['operation_id']and any(s['session_id']==identity['a1']['session_id']for s in item['entry']['sessions'])]
        assert len(deliveries)==1 and deliveries[0]['delivery_semantics']['execution_outcome']=='succeeded'
        (root/'focus-host-predicate.json').write_text(json.dumps(dict(**exact,hostRevision=terminal['board']['revision'],deliveryId=deliveries[0]['id']),indent=2)+'\\n')
        run('close',**exact,hostRevision=terminal['board']['revision'],deliveryId=deliveries[0]['id'])
"""+source[end:]
assert source.count("cli('open','open',")==1
source=source.replace("cli('open','open',","cli('launch','open',")
exec(compile(source,str(HERE/'run.py'),'exec'))
