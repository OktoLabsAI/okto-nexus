"""Retain login installation progress separately from the canonical setup receipt."""
from ....application.terminal_connection import ConnectionError, document_revision
from .native_input import display_text


def selected(document):
    return document.get('login_start_plan') or document.get('selection', {}).get('login_start')


def display(plan):
    scope = plan['scope']
    print('Startup: user login | ' + display_text(scope['principal']))
    print('Server home: ' + display_text(scope['home']))
    print('Interpreter: ' + display_text(scope['executable']))
    for effect in plan['effects']:
        print('- ' + display_text(effect))


def separate_review(document):
    value = dict(state='login_start_review', server_id=document['server_id'],
        agent_id=document['selection']['agent'], binding_id=document['result']['binding']['binding_id'],
        login_start=selected(document))
    return dict(value, review_revision=document_revision(value))


def initial_review_covers_login(document):
    if not document.get('review_request') or document.get('login_start_plan'):
        return False
    review = {key: document[key] for key in ('server_id', 'selection', 'version_check_required', 'effects')}
    if 'identity_creation' in document:
        review['identity_creation'] = document['identity_creation']
    review['request'] = document['review_request']
    return document_revision(review) == document['review_revision']


def authorize(document, save, approval):
    if document['state'] != 'done':
        raise ConnectionError('SETUP_REQUIRED', 'Complete the canonical project setup before installing login startup.')
    operation = document.get('login_start_operation')
    if operation:
        return
    review = separate_review(document)
    if not initial_review_covers_login(document) and approval != review['review_revision']:
        raise ConnectionError('REVIEW_REQUIRED', 'Approve the displayed login startup review before changing the local service.')
    document['login_start_operation'] = dict(state='pending', plan_revision=selected(document)['plan_revision'])
    save(document)  # Persist authorized intent before any native effect.


def resume(service, document, save, *, timeout):
    plan, operation = selected(document), document.get('login_start_operation')
    if (not plan or not operation or document['state'] != 'done' or
            operation.get('plan_revision') != plan['plan_revision']):
        raise ConnectionError('LOGIN_START_CHECKPOINT_INVALID', 'Inspect the retained project and login startup review.')
    if operation['state'] == 'done':
        return None  # Reconnect never reinstalls or reenables a later disabled task.
    if operation['state'] not in ('pending', 'installed'):
        raise ConnectionError('LOGIN_START_CHECKPOINT_INVALID', 'The login startup checkpoint is not recognized.')
    service.adapter.check_login_start_review(plan)
    try:
        return _resume(service, document, save, timeout=timeout)
    except (OSError, ValueError) as error:
        raise ConnectionError(getattr(error, 'code', 'LOGIN_START_UNCONFIRMED'),
            getattr(error, 'action', 'Inspect the retained login startup operation and resume this same project profile.'),
            possible_effect=True, stage='login_start') from None


def _resume(service, document, save, *, timeout):
    plan, operation = selected(document), document['login_start_operation']
    if operation['state'] == 'pending':
        if plan['action'] == 'install':
            result = service.install_user_service(timeout=timeout)
            complete = result.get('installation_state') == 'installed'
        elif plan['action'] == 'enable':
            result = service.enable_user_service(timeout=timeout)
            complete = result.get('enablement_confirmed') is True and result.get('enabled') is True
        else:
            result, complete = service.inspect(), True
        if not complete:
            return dict(state='login_start_pending', setup_state='configured', service=result,
                next_action='Resume this same connect profile. The canonical setup receipt is retained; no model test is repeated.')
        operation['state'] = 'installed'
        save(document)
    # The normal lifecycle resolves the installed supervisor. It never falls
    # back to an independent detached process when registration is uncertain.
    result = service.ensure_running(timeout=timeout)
    if result['state'] != 'ready':
        return dict(state='login_start_pending', setup_state='configured', service=result,
            next_action='Inspect the selected user service and resume this same profile.')
    operation['state'] = 'done'
    save(document)
    return result
