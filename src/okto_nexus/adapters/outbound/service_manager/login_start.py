"""Concrete, secret-free login startup review over the existing user installer."""
from nexus_connector_core.user_service_definition import windows_definition_digest, windows_with_enabled

from .context import document_revision, validate_context
from .identity import effective_principal
from .installation import InstallationError, SUPERVISOR, context_digest


def scope(adapter):
    context = validate_context(adapter.context)
    return dict(component='server', instance_id=adapter.installation.instance_id,
        principal=effective_principal(), supervisor=SUPERVISOR,
        home=str(adapter.home), database=str(adapter.database),
        executable=context['executable'], cwd=context['cwd'], context_digest=context_digest(context))


def review(adapter):
    installation = adapter.installation
    installation.prepare(adapter.context)  # Includes read-only native validation.
    receipt, task = installation.observe() if installation.receipt() else (None, None)
    action = 'install' if receipt is None else 'reuse' if task.enabled else 'enable'
    result = dict(format=1, scope=scope(adapter), action=action,
        native_digest=task.digest if task else None,
        enabled_digest=windows_definition_digest(windows_with_enabled(task.xml, True)) if task else None,
        effects=[
            'Start this Server at login for the effective user; credentials remain in that user context.',
            'No system service, elevated privileges, availability before login or after logout is requested.',
        ])
    if action == 'install':
        result['effects'].append('After setup is saved, drain and stop this Server, install its user logon task, then start it through that task. Active work may delay the transition; no forced termination is used.')
    elif action == 'enable':
        result['effects'].append('Enable the existing reviewed user task; preserve its execution context and definition.')
    else:
        result['effects'].append('Reuse the already enabled user task without replacing or restarting it.')
    return dict(result, plan_revision=document_revision(result))


def validate(adapter, plan):
    """Fence context and native changes, allowing only the retained intent's result."""
    if (plan.get('format') != 1 or plan.get('action') not in ('install', 'enable', 'reuse') or
            document_revision({k: v for k, v in plan.items() if k != 'plan_revision'}) != plan.get('plan_revision') or
            plan['scope'] != scope(adapter)):
        raise InstallationError('LOGIN_START_REVIEW_CHANGED', 'Review login startup again for the selected user, instance and execution context.')
    installation = adapter.installation
    receipt = installation.receipt()
    if plan['action'] == 'install':
        installation.prepare(adapter.context)
        if receipt is not None and receipt['state'] == 'installed':
            _, task = installation.observe()
            if not task.enabled:
                raise InstallationError('LOGIN_START_REVIEW_CHANGED', 'The installed task was disabled. Preserve that choice and review enablement explicitly.')
        return
    if receipt is None or receipt.get('context_digest') != plan['scope']['context_digest']:
        raise InstallationError('LOGIN_START_REVIEW_CHANGED', 'The reviewed user task or its execution context changed.')
    pending = receipt.get('enablement')
    if pending:
        if (plan['action'] != 'enable' or pending.get('target') is not True or
                pending.get('from_digest') != plan['native_digest']):
            raise InstallationError('LOGIN_START_REVIEW_CHANGED', 'Another enablement transition is pending.')
        installation._check_context(receipt)
        return  # set_enabled validates/reconciles the exact retained native change.
    _, task = installation.observe()
    allowed = {plan['native_digest']}
    if plan['action'] == 'enable':
        allowed.add(plan['enabled_digest'])
    if task.digest not in allowed:
        raise InstallationError('LOGIN_START_REVIEW_CHANGED', 'The user task changed after review. Its current definition was preserved.')
