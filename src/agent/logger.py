import time
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import config


class CallLogEntry:
    """Accumulates data for a single LLM call or key function execution."""

    def __init__(self, path: Path, call_type: str, metadata: dict[str, Any]):
        self.path = path
        self.call_type = call_type
        self.metadata = metadata
        self.system_prompt: str | None = None
        self.user_messages: list | None = None
        self.response: str | None = None
        self.prompt_tokens: int | None = None
        self.completion_tokens: int | None = None
        self.duration_ms: int | None = None
        self.error: str | None = None

    def set_system_prompt(self, text: str):
        self.system_prompt = text

    def set_user_messages(self, messages: list):
        self.user_messages = messages

    def set_response(self, text: str):
        self.response = text

    def set_token_usage(self, prompt: int, completion: int):
        self.prompt_tokens = prompt
        self.completion_tokens = completion

    def set_error(self, error: str):
        self.error = error

    def write(self):
        """Write the complete log entry to a Markdown file."""
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"# LLM Call: {self.call_type}\n")
            f.write(f"- **Timestamp:** {datetime.now(timezone.utc).isoformat()}\n")
            for k, v in self.metadata.items():
                f.write(f"- **{k}:** {v}\n")
            if self.duration_ms is not None:
                f.write(f"- **Duration:** {self.duration_ms}ms\n")
            f.write("\n---\n\n")

            if self.system_prompt:
                f.write("## System Prompt\n\n```\n")
                f.write(self.system_prompt)
                f.write("\n```\n\n---\n\n")

            if self.user_messages:
                f.write("## User Messages\n\n")
                for i, msg in enumerate(self.user_messages):
                    f.write(f"### Message {i + 1}\n\n```\n{msg}\n```\n\n")
                f.write("---\n\n")

            if self.response is not None:
                f.write("## Response\n\n```\n")
                f.write(self.response)
                f.write("\n```\n\n---\n\n")

            if self.error:
                f.write("## Error\n\n```\n")
                f.write(self.error)
                f.write("\n```\n\n---\n\n")

            f.write("## Token Usage\n\n")
            if self.prompt_tokens is not None and self.completion_tokens is not None:
                total = self.prompt_tokens + self.completion_tokens
                f.write(f"- Prompt: {self.prompt_tokens} tokens\n")
                f.write(f"- Completion: {self.completion_tokens} tokens\n")
                f.write(f"- Total: {total} tokens\n")
            else:
                f.write("- Not recorded\n")


class CallLogger:
    """Logs complete LLM call data to individual Markdown files."""

    def __init__(self, log_dir: str | Path):
        self.log_dir = Path(log_dir)

    @contextmanager
    def capture(self, call_type: str, **metadata):
        """Context manager: wraps an LLM call, saves full input + output.

        Usage:
            with logger.capture("outline_gen", model="gpt-4o") as entry:
                entry.set_system_prompt(prompt)
                entry.set_user_messages([user_msg])
                result = llm_client.chat(...)
                entry.set_response(result)
        """
        call_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        log_path = self.log_dir / f"{call_id}_{call_type}.md"
        entry = CallLogEntry(log_path, call_type, metadata)
        start = time.monotonic()
        try:
            yield entry
        except Exception as e:
            entry.set_error(str(e))
            raise
        finally:
            entry.duration_ms = int((time.monotonic() - start) * 1000)
            entry.write()


logger = CallLogger(config.CALLS_LOG_DIR)
