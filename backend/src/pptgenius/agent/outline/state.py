"""Outline agent state — shared across generator and evaluator nodes."""

from __future__ import annotations

from typing import Annotated
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
        Current user message / task description.
    outline_id : int | None
        ID of the outline being worked on.  ``None`` means create new.
    evaluated : bool
        Controls routing: ``False`` → evaluator, ``True`` → generator.
    iteration : int
        Generator run count (used for max-iteration stop).
    eval_score : float | None
        Latest evaluation total score (0-10).
    eval_suggestions : str
        Latest evaluator improvement suggestions.
    mode : str
        ``"max_iteration"`` | ``"pass_score"`` | ``"mix"``.
    max_iterations : int
        Hard cap on generator runs.
    pass_score : float
        Score threshold (0-10).
    design_rationale : str
        Latest generator design rationale.
    design_rationales : list[str]
        Accumulated rationales from every generator run.
    final_outline_data : dict | None
        Serialised outline + slides for frontend emission.
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
    design_rationales: Annotated[list[str], operator.add]
    final_outline_data: dict | None
    messages: Annotated[list[BaseMessage], operator.add]
