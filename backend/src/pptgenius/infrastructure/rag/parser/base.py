"""Shared types for document parsers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDocument:
    """Normalised output from any parser."""

    file_path: str
    file_type: str
    text: str
    char_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.char_count:
            self.char_count = len(self.text)


def _normalise_text(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        cleaned.append(stripped)
    # Collapse 3+ consecutive blank lines → 2
    result: list[str] = []
    blanks = 0
    for line in cleaned:
        if line == "":
            blanks += 1
            if blanks <= 2:
                result.append(line)
        else:
            blanks = 0
            result.append(line)
    return "\n".join(result).strip()
