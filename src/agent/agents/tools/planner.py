"""Tools for creating and revising execution plans."""

from datetime import datetime, timezone

from .registry import register
from ...models.outline import Plan, TodoItem
from ...llm import create_llm_client
from ...logger import logger


@register
def create_plan(goal: str, context: str = "") -> dict:
    """Analyze a user request and break it down into an ordered TodoList.

    Args:
        goal: The overall goal or user request.
        context: Additional context (RAG results, conversation history).

    Returns:
        Dict with plan containing goal, items (ordered todos with descriptions).
    """
    client = create_llm_client()
    system = (
        "You are a planning agent. Break down the user's PPT generation request "
        "into 3-6 ordered steps (TodoItems). Each step should specify:\n"
        "- id: sequential number\n"
        "- description: what to do\n"
        "- tools_needed: which tools might be needed\n"
        "- depends_on: ids of steps this depends on (0 for none)\n\n"
        "Available tools: query_knowledge_base, query_database, search_web, "
        "select_template, generate_chart, generate_table, select_image, "
        "modify_slide_content, modify_slide_layout, generate_ppt\n\n"
        "Return JSON with format: {items: [{id, description, tools_needed, depends_on}]}"
    )

    user_msg = f"Goal: {goal}\n\nContext:\n{context}"

    with logger.capture("create_plan", model=client.default_model if hasattr(client, 'default_model') else 'mock') as cap:
        cap.set_system_prompt(system)
        cap.set_user_messages([user_msg])

        try:
            plan_result, raw = client.chat_structured(
                response_model=Plan,
                system=system,
                messages=[user_msg],
            )
            cap.set_response(raw.text)
            cap.set_token_usage(raw.prompt_tokens, raw.completion_tokens)

            return {
                "plan": plan_result.model_dump(),
            }
        except Exception:
            # Fallback: generate a default plan
            default_plan = Plan(
                goal=goal,
                items=[
                    TodoItem(id=1, description="Search for relevant information", tools_needed=["search_web"], depends_on=[]),
                    TodoItem(id=2, description="Query knowledge base for related content", tools_needed=["query_knowledge_base"], depends_on=[1]),
                    TodoItem(id=3, description="Select or design a PPT template", tools_needed=["select_template"], depends_on=[]),
                    TodoItem(id=4, description="Generate the PPT from collected information", tools_needed=["generate_ppt"], depends_on=[2, 3]),
                ],
            )
            cap.set_response(default_plan.model_dump_json())
            return {"plan": default_plan.model_dump()}


@register
def revise_plan(plan_json: str, feedback: str) -> dict:
    """Revise an existing plan based on execution feedback.

    Args:
        plan_json: JSON string of the current Plan.
        feedback: What went wrong or what changed.

    Returns:
        Dict with updated plan.
    """
    import json
    try:
        current = json.loads(plan_json)
    except Exception as e:
        return {"error": f"Invalid plan JSON: {e}"}

    current["revised_at"] = datetime.now(timezone.utc).isoformat()
    return {
        "plan": current,
        "message": f"Plan updated based on: {feedback}",
    }
