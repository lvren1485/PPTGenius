from datetime import datetime, timezone
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """A single turn in the conversation history."""

    session_id: str
    turn_index: int
    role: str  # user | agent | system
    message: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class LLMCallRecord(BaseModel):
    """Record of a single LLM API call."""

    id: str
    session_id: str
    turn_id: int
    model: str
    system_prompt: str | None = None
    user_prompt: str | None = None
    response: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ToolCallRecord(BaseModel):
    """Record of a single tool execution."""

    session_id: str
    turn_id: int
    llm_call_id: str | None = None
    tool_name: str
    tool_input: str
    tool_output: str | None = None
    duration_ms: int = 0
    status: str = "success"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
