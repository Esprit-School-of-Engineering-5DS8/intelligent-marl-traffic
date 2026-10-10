"""agents.llm — LLM client layer, directive contract, generic agent."""

from agents.llm.agent import AgentCall, LLMAgent, load_system_prompt
from agents.llm.client import (
    CallLogger,
    LLMClient,
    LLMError,
    LLMResponse,
    LLMResponseError,
    MockLLM,
    OpenAICompatClient,
    ReplayLLM,
    prompt_hash,
)
from agents.llm.schemas import (
    ACTION_TO_AXIS,
    AXES,
    AXIS_TO_ACTION,
    DIRECTIVE_ENVELOPE_SCHEMA,
    DIRECTIVE_TYPES,
    EMPTY_ENVELOPE,
    ROLE_PERMISSIONS,
    Directive,
    EnvelopeResult,
    RejectedDirective,
    SchemaError,
    validate_directive,
    validate_envelope,
)

__all__ = [
    "AgentCall", "LLMAgent", "load_system_prompt",
    "CallLogger", "LLMClient", "LLMError", "LLMResponse", "LLMResponseError",
    "MockLLM", "OpenAICompatClient", "ReplayLLM", "prompt_hash",
    "ACTION_TO_AXIS", "AXES", "AXIS_TO_ACTION", "DIRECTIVE_ENVELOPE_SCHEMA",
    "DIRECTIVE_TYPES", "EMPTY_ENVELOPE", "ROLE_PERMISSIONS", "Directive",
    "EnvelopeResult", "RejectedDirective", "SchemaError", "validate_directive",
    "validate_envelope",
]
