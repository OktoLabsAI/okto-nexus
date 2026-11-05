"""Canonical operator agent creation, reusable inside an existing transaction."""
from .capabilities import CapabilityCatalogService
from ..domain.approvals import OPERATOR_AGENT_ID, is_reserved_agent_id
from ..domain.permissions import validate_permission_flags
from ..domain.routing import normalize_capabilities
from ..errors import ErrorCode, OktoNexusError


def validate_agent_id(agent_id):
    if not isinstance(agent_id, str) or not 1 <= len(agent_id) <= 128 or not agent_id.strip():
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR, 'A nonempty agent ID of at most 128 characters is required.', {})
    if is_reserved_agent_id(agent_id):
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            f"agent_id '{agent_id}' is reserved for the human operator and cannot be created.",
            {'agent_id': agent_id, 'reserved': OPERATOR_AGENT_ID})


def require_available_id(deps, uow, agent_id):
    validate_agent_id(agent_id)
    if deps.repos.agents.get(uow, agent_id) is not None:
        raise OktoNexusError(ErrorCode.VALIDATION_ERROR,
            'agent already exists; use PATCH to update or regenerate-key to rotate its key.', {'agent_id': agent_id})


def create_agent_in_uow(deps, uow, auth, *, agent_id, role=None, capabilities=None,
                        metadata=None, color=None, permissions=None, preset_id=None):
    """The authenticated operator caller owns authorization and the transaction.

    Creation never adopts an existing identity. The canonical key issuer returns
    plaintext once; managed setup intentionally does not export that material.
    """
    require_available_id(deps, uow, agent_id)
    if isinstance(capabilities, list):
        capabilities = {str(item): True for item in capabilities}
    announced = normalize_capabilities(capabilities)
    if announced:
        CapabilityCatalogService(catalog=deps.repos.capability_catalog).ensure_registered(uow, announced, field='capabilities')
    if permissions is not None:
        permissions = validate_permission_flags(permissions)
    agents = deps.repos.agents
    agent = agents.upsert(uow, agent_id=agent_id, role=role, capabilities=capabilities,
                          metadata=metadata, color=color)
    if permissions is not None or preset_id is not None:
        agents.set_permissions(uow, agent_id=agent.agent_id, permissions=permissions, preset_id=preset_id)
    plaintext = auth.issue_key(uow, agent_id=agent.agent_id)
    return agents.get(uow, agent.agent_id), plaintext
