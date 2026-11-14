"""Pure bounded selection for the existing normal containment callbacks.

The caller persists each selected action before dispatch and retains exact
scope. This selector performs no HTTP, process action, retry or inference.
"""
import time

def select(*,expected_owner,observed_owner,physical_exit,actions,exact_turn,
           turn_state,now,deadline):
    if physical_exit is not None:
        if (all(physical_exit.get(key)==expected_owner[key] for key in ('pid','birth_filetime','generation'))
                and physical_exit.get('retained_handle') is True
                and physical_exit.get('exit_confirmed') is True
                and physical_exit.get('force_used') is False):
            return {'action':'COMPLETE','reason':'EXACT_PHYSICAL_EXIT'}
    if now>=deadline:
        return {'action':'UNCONFIRMED','reason':'NORMAL_CONTAINMENT_DEADLINE','new_posts_allowed':False}
    if observed_owner is None:
        return {'action':'OBSERVE','reason':'OWNER_UNCONFIRMED','new_posts_allowed':False}
    if not all(observed_owner.get(key)==expected_owner[key] for key in ('pid','birth_filetime','generation')):
        return {'action':'UNCONFIRMED','reason':'OWNER_IDENTITY_CHANGED','new_posts_allowed':False}
    if observed_owner.get('state') not in ('ready','stopping') or observed_owner.get('ready_for_queries') is not True:
        return {'action':'OBSERVE','reason':'CANONICAL_CONTROL_NOT_READY','new_posts_allowed':False}
    stops=[item for item in actions if item['kind']=='normal_stop']
    interrupts=[item for item in actions if item['kind']=='turn_interrupt']
    if len(stops)>2 or len(interrupts)>1:
        raise ValueError('FINITE_CONTAINMENT_ALLOCATION_EXCEEDED')
    if any(item.get('returned') is not True for item in actions):
        return {'action':'OBSERVE','reason':'SELECTED_ACTION_NOT_CONFIRMED_RETURNED','new_posts_allowed':False}
    if not stops:
        return {'action':'NORMAL_STOP','ordinal':1}
    if turn_state=='active' and not interrupts:
        required=('session_id','operation_id','native_turn_id')
        if not exact_turn or not all(type(exact_turn.get(k)) is str and exact_turn[k] for k in required):
            if len(stops)<2:return {'action':'NORMAL_STOP','ordinal':2}
            return {'action':'OBSERVE','reason':'EXACT_TURN_UNCONFIRMED','new_posts_allowed':False}
        return {'action':'TURN_INTERRUPT','target':{k:exact_turn[k] for k in required},
                'maximum_resolve_posts':1,'maximum_admit_posts':1,'retry_allowed':False}
    if interrupts and interrupts[0].get('admitted') is not True and turn_state!='terminal':
        return {'action':'OBSERVE','reason':'INTERRUPT_OUTCOME_UNCONFIRMED','new_posts_allowed':False}
    if len(stops)<2:
        # A normal stop is scoped to the exact owner, not to a guessed native
        # turn. A missing turn prevents interrupt but need not prevent drain.
        return {'action':'NORMAL_STOP','ordinal':2}
    # A stop exit, even zero, is never proof of native/service exit.
    return {'action':'OBSERVE','reason':'WAIT_EXACT_PHYSICAL_EXIT','new_posts_allowed':False}

def require_boundary(*,expected_owner,observed_owner,now,deadline):
    """Call immediately before each canonical resolve/admit or normal-stop POST."""
    if now>=deadline:
        raise RuntimeError('NORMAL_CONTAINMENT_DEADLINE')
    if observed_owner is None or not all(observed_owner.get(key)==expected_owner[key]
            for key in ('pid','birth_filetime','generation')):
        raise RuntimeError('OWNER_IDENTITY_UNCONFIRMED')
    if observed_owner.get('state') not in ('ready','stopping') or observed_owner.get('ready_for_queries') is not True:
        raise RuntimeError('CANONICAL_CONTROL_NOT_READY')

def run(*,expected_owner,exact_turn,first_stop_result,observe_owner,observe_turn,
        physical_exit,interrupt,normal_stop,save,close_admissions,clock=time.monotonic,sleep=time.sleep,
        timeout_seconds=180):
    """Run the existing finite controls after its first normal stop returned.

    Every effect callback receives a boundary guard to recheck immediately
    before each actual POST. Unknown results are never replayed.
    """
    close_admissions()
    started=clock();deadline=started+min(timeout_seconds,180)
    actions=[{'kind':'normal_stop','returned':True,'result':first_stop_result}]
    observation_errors=[]
    def boundary():
        # Check time before the GET too; no control after an already expired bound.
        if clock()>=deadline:raise RuntimeError('NORMAL_CONTAINMENT_DEADLINE')
        owner=observe_owner()
        require_boundary(expected_owner=expected_owner,observed_owner=owner,now=clock(),deadline=deadline)
    while True:
        exited=physical_exit()
        owner=None
        if not exited and clock()<deadline:
            try:owner=observe_owner()
            except Exception as error:observation_errors=(observation_errors+[type(error).__name__])[-8:]
        turn_state='unknown'
        if clock()<deadline and owner is not None and all(owner.get(k)==expected_owner[k] for k in ('pid','birth_filetime','generation')):
            try:turn_state=observe_turn(exact_turn)
            except Exception as error:observation_errors=(observation_errors+[type(error).__name__])[-8:]
        selected=select(expected_owner=expected_owner,observed_owner=owner,physical_exit=exited,
            actions=actions,exact_turn=exact_turn,turn_state=turn_state,now=clock(),deadline=deadline)
        if selected['action'] in ('COMPLETE','UNCONFIRMED'):
            result={**selected,'actions':actions,'elapsed_seconds':clock()-started,
                    'physical_exit':exited,'productive_admissions_closed':True,'force_used':False,
                    'observation_errors':observation_errors}
            save('result',result);return result
        if selected['action'] in ('NORMAL_STOP','TURN_INTERRUPT'):
            kind='turn_interrupt' if selected['action']=='TURN_INTERRUPT' else 'normal_stop'
            name='interrupt' if kind=='turn_interrupt' else 'normal-stop-2'
            # Exclusive reservation is outside the catch: duplicate execution refuses.
            save(name+'-reserved',{'kind':kind,'selection':selected,'deadline_monotonic':deadline})
            item={'kind':kind,'returned':False};actions.append(item)
            try:
                boundary()
                if kind=='turn_interrupt':
                    value=interrupt(exact_turn,boundary,deadline)
                    item.update(returned=True,admitted=value.get('admitted') is True,result=value)
                else:
                    value=normal_stop(boundary,deadline)
                    item.update(returned=True,result=value)
            except Exception as error:
                item.update(returned=True,outcome='UNCONFIRMED',error_type=type(error).__name__,code=getattr(error,'code',None))
            save(name+'-returned',item)
        remaining=deadline-clock()
        if remaining>0:sleep(min(.5,remaining))
