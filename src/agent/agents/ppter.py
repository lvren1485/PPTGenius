"""PPT Agent: Plan-then-Execute loop for generating presentations."""

import json

from ..llm import create_llm_client, LLMResponse
from ..logger import logger
from ..models.outline import PresentationOutline
from .tools import list_tools, execute_tool
from .tools.registry import TOOL_REGISTRY


class PPTAgent:
    """Main PPT generation agent with Plan-then-Execute loop."""

    def __init__(self):
        self.client = create_llm_client()
        self.context: list[str] = []
        self.plan: dict | None = None

    def run(self, topic: str) -> dict:
        """Full Plan-then-Execute pipeline for PPT generation.

        Returns dict with plan, execution log, and generated output.
        """
        # 1. Plan phase
        self._log("Planning phase: analyzing request")
        plan_result = execute_tool(
            "create_plan",
            goal=topic,
            context="\n".join(self.context[-5:]),
        )
        self.plan = plan_result.get("plan")
        if not self.plan:
            return {"error": "Failed to create plan", "plan": None}

        items = self.plan.get("items", [])
        self._log(f"Plan created with {len(items)} items")

        # 2. Execute phase - work through each todo
        execution_log = []
        for item in items:
            todo_result = self._execute_todo(item)
            execution_log.append(todo_result)
            if todo_result.get("error"):
                self._log(f"Todo {item['id']} failed: {todo_result['error']}")
                continue

        # 3. Generate final output
        output = self._generate_output(topic)
        return {
            "plan": self.plan,
            "execution_log": execution_log,
            "output": output,
        }

    def _execute_todo(self, todo: dict) -> dict:
        """Execute a single todo item using ReAct loop."""
        todo_id = todo["id"]
        description = todo["description"]
        self._log(f"Executing todo {todo_id}: {description}")

        system = (
            "You are executing a step in a PPT generation plan. "
            "Use the available tools to accomplish the current task. "
            "When the task is complete, respond with 'DONE'.\n\n"
            f"Available tools: {json.dumps([t['name'] for t in list_tools()])}"
        )
        messages = [
            f"Current task: {description}\n"
            f"Context: {'\n'.join(self.context[-3:])}"
        ]

        max_iterations = 5
        for iteration in range(max_iterations):
            with logger.capture(
                "react_iteration",
                model=self.client.default_model if hasattr(self.client, 'default_model') else 'mock',
                todo_id=str(todo_id),
                iteration=str(iteration),
            ) as cap:
                cap.set_system_prompt(system)
                cap.set_user_messages(messages)

                response = self.client.chat(system=system, messages=messages)
                cap.set_response(response.text)
                cap.set_token_usage(response.prompt_tokens, response.completion_tokens)

                text = response.text.strip()

            # Parse tool call from response
            if text.upper() == "DONE" or "DONE" in text:
                self._log(f"Todo {todo_id} completed")
                return {"todo_id": todo_id, "status": "completed", "iterations": iteration + 1}

            # Try to find and execute a tool call
            tool_result = self._try_tool_call(text)
            if tool_result:
                messages.append(f"Tool result: {json.dumps(tool_result, ensure_ascii=False)}")
                self.context.append(f"Todo {todo_id}: {tool_result}")

        return {"todo_id": todo_id, "status": "completed", "iterations": max_iterations}

    def _try_tool_call(self, text: str) -> dict | None:
        """Try to parse and execute a tool call from LLM response."""
        for tool_name in TOOL_REGISTRY:
            if tool_name in text:
                self._log(f"Auto-executing tool: {tool_name}")
                return execute_tool(tool_name)
        return None

    def _generate_output(self, topic: str) -> dict:
        """Generate the final output based on execution context."""
        with logger.capture("generate_output", topic=topic) as cap:
            system = "Generate a PPT outline JSON from the execution context."
            response = self.client.chat(
                system=system,
                messages=[
                    f"Topic: {topic}",
                    f"Context: {'\n'.join(self.context)}",
                ],
            )
            cap.set_response(response.text)

        try:
            outline = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            outline = {
                "topic": topic,
                "slides": [
                    {"title": topic, "subtitle": "", "bullets": [], "layout_type": "title"},
                    {"title": "Overview", "bullets": ["Key topics covered"], "layout_type": "content"},
                    {"title": "Summary", "bullets": ["Thank you"], "layout_type": "ending"},
                ],
            }

        return {
            "outline": outline,
            "slide_count": len(outline.get("slides", [])),
        }

    def _log(self, message: str):
        """Internal logging."""
        print(f"[PPTAgent] {message}")
