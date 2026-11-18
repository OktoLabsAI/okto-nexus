"""Initial typed wire contract for exact session interaction.

This module registers no routes or authority. The coordinator must validate
the scope and generation again at the canonical effect boundary.
"""

from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ....domain.execution.keys import SessionKey, SessionOwnerGeneration
from ....domain.session_interaction import (
    MAX_INPUT_BYTES,
    MAX_SQLITE_INTEGER,
    InputDeliveryState,
    InputScope,
    validate_input_text,
)


def unicode_id(value: str) -> str:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("An identifier cannot contain an unpaired surrogate.")
    return value


Identifier = Annotated[str, Field(min_length=1, max_length=160), AfterValidator(unicode_id)]
Generation = Annotated[int, Field(ge=1, le=MAX_SQLITE_INTEGER)]
Revision = Annotated[int, Field(ge=0, le=MAX_SQLITE_INTEGER)]


class _Document(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ExactSessionScope(_Document):
    server_id: Identifier
    executor_id: Identifier
    binding_id: Identifier
    workspace_id: Identifier
    workspace_binding_id: Identifier
    agent_id: Identifier
    session_id: Identifier

    def session_key(self) -> SessionKey:
        return SessionKey(self.server_id, self.executor_id, self.session_id)

    def input_scope(self, generation: int) -> InputScope:
        return InputScope(self.session_key(), SessionOwnerGeneration(generation), self.binding_id,
                          self.workspace_id, self.workspace_binding_id, self.agent_id)


class ScopedInteraction(_Document):
    scope: ExactSessionScope
    expected_session_generation: Generation
    capability_revision: Identifier

    def owner_generation(self) -> SessionOwnerGeneration:
        return SessionOwnerGeneration(self.expected_session_generation)

    def input_scope(self) -> InputScope:
        return self.scope.input_scope(self.expected_session_generation)


class TextInput(_Document):
    type: Literal["text"]
    text: Annotated[str, Field(min_length=1, max_length=MAX_INPUT_BYTES)]

    @field_validator("text")
    @classmethod
    def bounded_utf8(cls, text: str) -> str:
        return validate_input_text(text)


class InputRequest(ScopedInteraction):
    client_intent_id: Identifier
    content: Annotated[list[TextInput], Field(min_length=1, max_length=1)]


class EnqueueInput(InputRequest):
    mode: Literal["next_turn"] = "next_turn"


class NativeTurnTarget(_Document):
    kind: Literal["native_turn"]
    turn_id: Identifier


class ObservedRunTarget(_Document):
    kind: Literal["observed_run"]
    run_ref: Identifier


TurnTarget = Annotated[NativeTurnTarget | ObservedRunTarget, Field(discriminator="kind")]


class SteerInput(InputRequest):
    target: TurnTarget
    confirmed_effect_revision: Identifier


class QueueChange(ScopedInteraction):
    expected_queue_revision: Revision


class QueuePauseChange(QueueChange):
    paused: bool


class CancelInput(QueueChange):
    expected_input_revision: Revision


class PromoteInput(CancelInput):
    target: TurnTarget
    confirmed_effect_revision: Identifier


class InterruptInput(QueueChange):
    client_intent_id: Identifier
    target: TurnTarget


class InputReceipt(_Document):
    scope: ExactSessionScope
    session_owner_generation: Generation
    input_id: Identifier
    enqueue_sequence: Generation
    input_revision: Revision
    queue_revision: Revision
    status: InputDeliveryState
    operation_id: Identifier | None
    possible_effect: bool

    @model_validator(mode="after")
    def distinct_delivery_boundary(self) -> "InputReceipt":
        claimed = self.status in {
            InputDeliveryState.DISPATCHING, InputDeliveryState.ACCEPTED_NATIVE,
            InputDeliveryState.DELIVERY_UNKNOWN,
        }
        if claimed and self.operation_id is None:
            raise ValueError("This delivery state requires its canonical operation.")
        if self.status is InputDeliveryState.DELIVERY_UNKNOWN and not self.possible_effect:
            raise ValueError("An unknown delivery must retain possible effect.")
        if not claimed and self.possible_effect:
            raise ValueError("This input state cannot represent a possible delivery.")
        return self


class InputQueueEntry(InputReceipt):
    can_cancel: bool


class InputQueueState(_Document):
    scope: ExactSessionScope
    session_owner_generation: Generation
    queue_revision: Revision
    paused: bool


class InputQueueSnapshot(InputQueueState):
    cancel_capability_revision: Identifier | None
    pause_capability_revision: Identifier | None
    items: Annotated[list[InputQueueEntry], Field(max_length=50)]
    next_cursor: str | None


class PrepareAttachment(ScopedInteraction):
    client_intent_id: Identifier
    intent: Literal["attach_live", "resume_saved"]
    access: Literal["read", "write"]


class CommandDescriptor(_Document):
    command_id: Identifier
    source: Literal["nexus", "native"]
    state: Literal["supported", "disabled_for_state", "denied_by_policy", "native_only", "unsupported", "unqualified"]
    reason: str | None
    requires_confirmation: bool


class SessionCommandCatalog(ScopedInteraction):
    version: Literal[1] = 1
    items: Annotated[list[CommandDescriptor], Field(max_length=100)]
