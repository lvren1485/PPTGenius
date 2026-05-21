"""Preset PPT template definitions."""

from dataclasses import dataclass, field
from .styles import SlideColors, SlideFonts


@dataclass
class Template:
    name: str
    colors: SlideColors
    fonts: SlideFonts
    description: str = ""


TEMPLATES: dict[str, Template] = {
    "professional-blue": Template(
        name="Professional Blue",
        colors=SlideColors(bg="#FFFFFF", text="#1A1A2E", accent="#16213E", highlight="#0F3460"),
        fonts=SlideFonts(title="Calibri", body="Calibri"),
        description="Clean blue-themed corporate design",
    ),
    "modern-teal": Template(
        name="Modern Teal",
        colors=SlideColors(bg="#F0F7F4", text="#2D3436", accent="#00B894", highlight="#00CEC9"),
        fonts=SlideFonts(title="Segoe UI", body="Segoe UI"),
        description="Fresh teal-green modern style",
    ),
    "warm-orange": Template(
        name="Warm Orange",
        colors=SlideColors(bg="#FFF8F0", text="#2D3436", accent="#E17055", highlight="#FDCB6E"),
        fonts=SlideFonts(title="Arial", body="Arial"),
        description="Warm orange accents for creative presentations",
    ),
    "minimal-gray": Template(
        name="Minimal Gray",
        colors=SlideColors(bg="#FAFAFA", text="#333333", accent="#636E72", highlight="#B2BEC3"),
        fonts=SlideFonts(title="Helvetica", body="Helvetica"),
        description="Clean minimalist monochrome",
    ),
}


def get_template(name: str = "professional-blue") -> Template:
    """Get a template by name, falling back to default."""
    return TEMPLATES.get(name, TEMPLATES["professional-blue"])
