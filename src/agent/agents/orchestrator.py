"""Orchestrator: coordinates the full PPT generation pipeline."""

import uuid
from datetime import datetime, timezone

from ..config import config
from ..logger import logger
from ..db.engine import init_db
from ..db.conversation import (
    create_session,
    get_session,
    add_turn,
    get_turns,
    update_session,
)
from ..rag.scanner import scan_resources
from .ppter import PPTAgent
from .reviewer import ReviewAgent


class Orchestrator:
    """Top-level coordinator for the PPT generation system."""

    def __init__(self):
        self.ppter = PPTAgent()
        self.reviewer = ReviewAgent()
        self.session_id: str | None = None

    def run(
        self,
        topic: str,
        session_id: str | None = None,
    ) -> dict:
        """Run the full PPT generation pipeline.

        Args:
            topic: User's presentation topic.
            session_id: Optional existing session ID for multi-turn.

        Returns:
            Dict with session_id, output_path, report_path, slide_count.
        """
        # Initialize
        config.ensure_dirs()
        init_db()

        # Session management
        if session_id and get_session(session_id):
            self.session_id = session_id
            history = get_turns(session_id)
            for turn in history:
                self.ppter.context.append(f"{turn['role']}: {turn['message']}")
            print(f"[Orchestrator] Restored session: {session_id}")
        else:
            self.session_id = session_id or uuid.uuid4().hex
            create_session(topic, session_id=self.session_id)
            print(f"[Orchestrator] New session: {self.session_id}")

        # Log user input
        add_turn(self.session_id, "user", topic)

        # Scan resources
        print("[Orchestrator] Scanning resources...")
        resources_processed = scan_resources()
        print(f"[Orchestrator] Processed {len(resources_processed)} files")

        # Run PPT Agent
        print("[Orchestrator] Starting PPT Agent...")
        result = self.ppter.run(topic)

        if result.get("error"):
            print(f"[Orchestrator] Error: {result['error']}")
            return {"error": result["error"], "session_id": self.session_id}

        # Determine output paths
        output_pptx = str(config.OUTPUT_DIR / f"{self.session_id}.pptx")
        output_report = str(config.OUTPUT_DIR / f"{self.session_id}_report.md")

        # Generate report
        print("[Orchestrator] Generating report...")
        report = self.reviewer.generate_report(
            session_id=self.session_id,
            topic=topic,
            slide_count=result.get("output", {}).get("slide_count", 0),
            execution_log=result.get("execution_log", []),
            resources_processed=resources_processed,
            output_path=output_pptx,
        )

        # Save report
        with open(output_report, "w", encoding="utf-8") as f:
            f.write(report)

        # Update session
        update_session(self.session_id, status="completed")

        # Log agent response
        add_turn(self.session_id, "agent",
                 f"Generated {result.get('output', {}).get('slide_count', 0)} slides")

        print(f"[Orchestrator] Done! PPT: {output_pptx}")
        print(f"[Orchestrator] Report: {output_report}")

        return {
            "session_id": self.session_id,
            "output_path": output_pptx,
            "report_path": output_report,
            "slide_count": result.get("output", {}).get("slide_count", 0),
            "plan": result.get("plan"),
        }
