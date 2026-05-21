"""PPT Agent: generates comprehensive presentation outlines via LLM."""

import json

from ..llm import create_llm_client
from ..logger import logger
from ..models.outline import PresentationOutline


OUTLINE_SYSTEM_PROMPT = """You are a professional presentation designer. Generate a detailed, comprehensive PowerPoint outline in JSON format.

Requirements:
1. Produce 10-12 slides covering the topic comprehensively
2. Mix layout types: title(1), section(2-3), content(5-7), two_column(1-2), ending(1)
3. Each content slide must have 3-5 detailed bullet points (10-20 words each)
4. Include a logical flow: introduction → sections → summary → Q&A/ending
5. Section slides act as chapter dividers between major topic sections

Response must be valid JSON with this exact schema:
{
    "topic": "string",
    "style_notes": "string (optional design suggestions)",
    "slides": [
        {
            "title": "slide title",
            "subtitle": "optional subtitle",
            "bullets": ["bullet1", "bullet2", ...],
            "layout_type": "title|section|content|two_column|ending"
        }
    ]
}

IMPORTANT: Content must be factual, specific, and professional. Avoid generic filler."""


class PPTAgent:
    """PPT Agent: generates comprehensive outlines via direct LLM calls."""

    def __init__(self):
        self.client = create_llm_client()
        self.context: list[str] = []
        self.plan: dict | None = None

    def run(self, topic: str) -> dict:
        """Full pipeline: plan → comprehensive outline generation."""
        self._log("Generating comprehensive outline...")

        # Generate the outline via LLM
        outline = self._generate_comprehensive_outline(topic)

        if not outline or not outline.get("slides"):
            self._log("LLM output invalid, using fallback outline")
            outline = self._fallback_outline(topic)

        slide_count = len(outline.get("slides", []))
        self._log(f"Generated outline with {slide_count} slides")

        return {
            "plan": {"goal": topic, "items": [], "created_at": ""},
            "execution_log": [],
            "output": {"outline": outline, "slide_count": slide_count},
        }

    def _generate_comprehensive_outline(self, topic: str) -> dict | None:
        """Call LLM to generate a comprehensive presentation outline."""
        with logger.capture("generate_outline", topic=topic) as cap:
            cap.set_system_prompt(OUTLINE_SYSTEM_PROMPT)

            user_msg = f"Create a detailed presentation outline about: {topic}"
            if self.context:
                user_msg += f"\n\nContext:\n" + "\n".join(self.context[-3:])

            cap.set_user_messages([user_msg])

            response = self.client.chat(
                system=OUTLINE_SYSTEM_PROMPT,
                messages=[user_msg],
            )
            cap.set_response(response.text)
            cap.set_token_usage(response.prompt_tokens, response.completion_tokens)

            text = response.text.strip()

        # Try parsing JSON from response
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        return None

    def _fallback_outline(self, topic: str) -> dict:
        """Fallback outline when LLM fails."""
        return {
            "topic": topic,
            "style_notes": "Professional presentation with blue theme",
            "slides": [
                {"title": topic, "subtitle": "A Comprehensive Overview", "bullets": [], "layout_type": "title"},
                {"title": "Introduction", "bullets": [f"Overview of {topic}", "Key concepts and definitions", "Why this matters today"], "layout_type": "content"},
                {"title": "Core Concepts", "bullets": ["Fundamental principles", "Key theories and frameworks", "Practical applications"], "layout_type": "content"},
                {"title": "Key Applications", "bullets": ["Industry use cases", "Real-world examples", "Impact and benefits"], "layout_type": "content"},
                {"title": "Thank You", "subtitle": "Questions?", "bullets": [], "layout_type": "ending"},
            ],
        }

    def _log(self, message: str):
        print(f"[PPTAgent] {message}")
