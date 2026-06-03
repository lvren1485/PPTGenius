"""PPT agent state — TypedDict shared across all PPT graph nodes."""

from __future__ import annotations

import operator
from typing import Annotated

from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class PPTState(TypedDict):
    # ── entry ──
    user_id: int
    conversation_id: int
    query: str
    outline_id: int

    # ── modify vs create ──
    is_modify: bool
    presentation_id: int | None

    # ── Phase 1 output ──
    color_scheme_id: int | None
    template_id: int | None
    selected_layouts: dict[str, dict]        # {layout_name: full_definition}
    style_rationale: str

    # ── Phase 2 progress ──
    current_slide_index: int
    total_slides: int
    ppt_mode: str                             # "super_freedom"

    # ── context ──
    outline_slides: list[dict]
    design_rationales: Annotated[list[str], operator.add]
    file_path: str

    # ── messages ──
    messages: Annotated[list[BaseMessage], operator.add]
