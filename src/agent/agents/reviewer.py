"""Review Agent: generates the work summary and improvement suggestions report."""

from datetime import datetime, timezone

from ..llm import create_llm_client
from ..logger import logger


class ReviewAgent:
    """Analyzes a generated PPT and produces a combined report."""

    def __init__(self):
        self.client = create_llm_client()

    def generate_report(
        self,
        session_id: str,
        topic: str,
        slide_count: int,
        execution_log: list[dict] | None = None,
        resources_processed: list[dict] | None = None,
        output_path: str | None = None,
    ) -> str:
        """Generate a Markdown report combining work summary and suggestions.

        Args:
            session_id: Unique session identifier.
            topic: Original presentation topic.
            slide_count: Number of slides in the generated PPT.
            execution_log: Log of what the agent did.
            resources_processed: List of RAG files processed.
            output_path: Path to the generated PPT file.

        Returns:
            Markdown string with the complete report.
        """
        report = [
            f"# PPT Generation Report",
            f"",
            f"- **Session ID:** `{session_id}`",
            f"- **Topic:** {topic}",
            f"- **Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"- **Slides:** {slide_count}",
            f"",
        ]

        if output_path:
            report.append(f"- **Output:** `{output_path}`")
            report.append(f"")

        # Resources processed
        if resources_processed:
            report.append(f"## Resources Processed")
            report.append(f"")
            report.append(f"| File | Type | Status |")
            report.append(f"|------|------|--------|")
            for r in resources_processed:
                report.append(f"| {r.get('path', '')} | {r.get('type', '')} | Processed |")
            report.append(f"")

        # Execution summary
        if execution_log:
            report.append(f"## Execution Summary")
            report.append(f"")
            report.append(f"| Step | Status | Iterations |")
            report.append(f"|------|--------|------------|")
            for step in execution_log:
                tid = step.get("todo_id", "?")
                status = step.get("status", "?")
                iters = step.get("iterations", "?")
                report.append(f"| {tid} | {status} | {iters} |")
            report.append(f"")

        # Improvement suggestions
        report.append(f"## Improvement Suggestions")
        report.append(f"")

        suggestions = self._generate_suggestions(topic, slide_count)
        if suggestions:
            for s in suggestions:
                report.append(f"- {s}")
        else:
            report.append(f"- No specific suggestions at this time.")
        report.append(f"")

        return "\n".join(report)

    def _generate_suggestions(self, topic: str, slide_count: int) -> list[str]:
        """Generate improvement suggestions via LLM or fallback defaults."""
        with logger.capture("review_suggestions", topic=topic) as cap:
            system = "You are a presentation quality reviewer. Suggest 3-5 improvements."
            response = self.client.chat(
                system=system,
                messages=[
                    f"Review this presentation: Topic='{topic}', {slide_count} slides. "
                    f"Suggest specific improvements."
                ],
            )
            cap.set_response(response.text)
            text = response.text.strip()

        if text and text != "[Mock LLM response]" and text != "[No API key configured]":
            lines = [l.strip("- *") for l in text.split("\n") if l.strip().startswith(("- ", "* "))]
            return lines[:5] if lines else [text[:200]]

        return [
            "Consider adding more data-driven charts to support key points.",
            "Ensure each slide has a clear takeaway message.",
            "Add speaker notes for smoother delivery.",
            "Consider adding a Q&A slide at the end.",
            "Verify that all sources are properly cited.",
        ]
