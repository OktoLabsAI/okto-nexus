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
    ClaudeSteerReceipt,
    InputDeliveryState,
    InputScope,
    PiSteerBoundary,
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


class ScopedSession(_Document):
    scope: ExactSessionScope
    expected_session_generation: Generation

    def owner_generation(self) -> SessionOwnerGeneration:
        return SessionOwnerGeneration(self.expected_session_generation)

    def input_scope(self) -> InputScope:
        return self.scope.input_scope(self.expected_session_generation)


class ScopedInteraction(ScopedSession):
    capability_revision: Identifier


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


class ClaudeOperationTarget(_Document):
    kind: Literal["claude_operation"]
    operation_id: Identifier


SteerTarget = Annotated[NativeTurnTarget | ObservedRunTarget | ClaudeOperationTarget, Field(discriminator="kind")]


class SteerInput(InputRequest):
    target: SteerTarget
    confirmed_effect_revision: Identifier
    expected_queue_revision: Revision


class QueueChange(ScopedInteraction):
    expected_queue_revision: Revision


class QueuePauseChange(QueueChange):
    paused: bool


class CancelInput(QueueChange):
    expected_input_revision: Revision


class PromoteInput(CancelInput):
    target: SteerTarget
    confirmed_effect_revision: Identifier


class InterruptInput(QueueChange):
    client_intent_id: Identifier
    target: TurnTarget


class InterruptTargetView(_Document):
    target: TurnTarget
    capability_revision: Identifier
    queue_revision: Revision


class InterruptAvailability(_Document):
    scope: ExactSessionScope
    session_owner_generation: Generation
    control: InterruptTargetView | None


class SteerTargetView(_Document):
    target: SteerTarget
    capability_revision: Identifier
    queue_revision: Revision
    effect: Literal["same_turn", "next_boundary", "interrupt_then_send"]
    effect_revision: Identifier


class SteerInputPreview(_Document):
    input_id: Identifier
    input_revision: Revision
    text_preview: Annotated[str, Field(max_length=200)]
    truncated: bool


class SteerAvailability(_Document):
    scope: ExactSessionScope
    session_owner_generation: Generation
    control: SteerTargetView | None
    queued_input: SteerInputPreview | None = None


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
    steer_submitted: bool = False
    reorientation: bool = False
    steer_boundary: PiSteerBoundary | None = None
    steer_compound: ClaudeSteerReceipt | None = None

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
        if self.steer_boundary is not None and (not self.reorientation or self.operation_id is None
                                                 or not self.possible_effect):
            raise ValueError("A Pi boundary status requires an admitted reorientation.")
        if self.steer_compound is not None and (not self.reorientation or self.operation_id is None
                                                or not self.possible_effect or self.steer_boundary is not None):
            raise ValueError("Claude progress requires its admitted compound reorientation.")
        return self


class InputQueueEntry(InputReceipt):
    can_cancel: bool
    can_promote: bool = False


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
    presentation: Literal["codex", "pi", "codex_remote", "pi_remote"] = "codex"
    expected_writer_epoch: Annotated[int, Field(ge=0, lt=MAX_SQLITE_INTEGER)] | None = None
    takeover: bool = False

    @model_validator(mode="after")
    def exact_writer_intent(self):
        if self.access == "write" and self.expected_writer_epoch is None:
            raise ValueError("Review the writer epoch before preparing a writer.")
        if self.access == "read" and (self.expected_writer_epoch is not None or self.takeover):
            raise ValueError("A reader cannot take over a writer.")
        return self


CommandId = Literal[
    "help", "status", "send", "steer", "interrupt", "compact", "model",
    "effort", "export", "fork", "clear", "resume",
]
CommandState = Literal["supported", "disabled_for_state", "denied_by_policy", "native_only", "unsupported", "unqualified"]
CommandHandler = Literal["catalog", "session_status", "enqueue", "review_steer", "review_interrupt"]
CommandArgument = Literal["message"]


class CommandDescriptor(_Document):
    command_id: CommandId
    label: str
    effect: str
    source: Literal["nexus", "native"]
    surface: Literal["dashboard", "native_terminal"]
    handler: CommandHandler | None
    arguments: tuple[CommandArgument, ...] = ()
    state: CommandState
    reason: str | None
    requires_confirmation: bool


class SessionCommandCatalog(_Document):
    version: Literal[1] = 1
    scope: ExactSessionScope
    session_owner_generation: Generation
    capability_revision: Identifier
    adapter_id: Identifier | None
    literal_text_supported: Literal[False] = False
    items: Annotated[tuple[CommandDescriptor, ...], Field(max_length=100)]


class ReadSessionCommand(ScopedSession):
    command: Literal["help", "status"]
    catalog_revision: Identifier


class EnqueueSessionCommand(EnqueueInput):
    command: Literal["send"]
    catalog_revision: Identifier
    confirmed: Literal[True]


class SteerSessionCommand(SteerInput):
    command: Literal["steer"]
    catalog_revision: Identifier
    confirmed: Literal[True]


class InterruptSessionCommand(InterruptInput):
    command: Literal["interrupt"]
    catalog_revision: Identifier
    confirmed: Literal[True]


SessionCommand = Annotated[
    ReadSessionCommand | EnqueueSessionCommand | SteerSessionCommand | InterruptSessionCommand,
    Field(discriminator="command"),
]
