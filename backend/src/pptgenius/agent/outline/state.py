"""Outline agent state — shared across generator and evaluator nodes."""

from __future__ import annotations

from typing import Annotated, Any
import operator

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class OutlineState(TypedDict):
    """State shared between generator and evaluator nodes.

    Fields
    ------
    user_id : int
    conversation_id : int
    query : str
        Current user message / task description. On revision rounds this
        carries the evaluator's suggestions from the previous round.
    outline_id : int | None
        ID of the outline being worked on.  ``None`` means we need to
        create a new one.
    evaluated : bool
        Whether the current outline has been evaluated.  Controls routing:
        ``False`` → evaluator, ``True`` → generator (revise).
    iteration : int
        How many times the generator has run (used for max-iteration stop).
    eval_score : float | None
        Latest evaluation total score (0-10).
    eval_suggestions : str
        Latest evaluator improvement suggestions.
    mode : str
        Stop mode: ``"max_iteration"`` | ``"pass_score"`` | ``"mix"``.
    max_iterations : int
        Hard cap on generator runs.
    pass_score : float
        Score threshold (0-10) for pass_score / mix modes.
    design_rationale : str
        Generator's design rationale for the latest outline.
    messages : list[BaseMessage]
        Conversation history passed from the chat layer.
    messages : Annotated[list[BaseMessage], operator.add]
        Accumulated messages across agent invocations.
    """

    user_id: int
    conversation_id: int
    query: str
    outline_id: int | None
    evaluated: bool
    iteration: int
    eval_score: float | None
    eval_suggestions: str
    mode: str
    max_iterations: int
    pass_score: float
    design_rationale: str
    messages: Annotated[list[BaseMessage], operator.add]
