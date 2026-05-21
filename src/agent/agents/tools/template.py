"""Tool for selecting or designing PPT templates."""

from .registry import register

# Available preset templates
_AVAILABLE_TEMPLATES = {
    "professional-blue": {
        "name": "Professional Blue",
        "colors": {"bg": "#FFFFFF", "text": "#1A1A2E", "accent": "#16213E", "highlight": "#0F3460"},
        "font": "Calibri",
        "description": "Clean blue-themed corporate design",
    },
    "modern-teal": {
        "name": "Modern Teal",
        "colors": {"bg": "#F0F7F4", "text": "#2D3436", "accent": "#00B894", "highlight": "#00CEC9"},
        "font": "Segoe UI",
        "description": "Fresh teal-green modern style",
    },
    "warm-orange": {
        "name": "Warm Orange",
        "colors": {"bg": "#FFF8F0", "text": "#2D3436", "accent": "#E17055", "highlight": "#FDCB6E"},
        "font": "Arial",
        "description": "Warm orange accents for creative presentations",
    },
    "minimal-gray": {
        "name": "Minimal Gray",
        "colors": {"bg": "#FAFAFA", "text": "#333333", "accent": "#636E72", "highlight": "#B2BEC3"},
        "font": "Helvetica",
        "description": "Clean minimalist monochrome",
    },
}


@register
def select_template(preference: str | None = None) -> dict:
    """Select a PPT template based on user preference or auto-select.

    Args:
        preference: Optional style description (e.g., "corporate", "creative", "minimal").

    Returns:
        Dict with template_name, colors, font, and other style info.
    """
    if preference:
        pref_lower = preference.lower()
        for key, tmpl in _AVAILABLE_TEMPLATES.items():
            if pref_lower in tmpl["description"].lower():
                return {"template_name": key, **tmpl}
        # Fallback: try to match keywords
        if any(w in pref_lower for w in ["corporate", "business", "professional"]):
            key = "professional-blue"
        elif any(w in pref_lower for w in ["creative", "modern", "fresh"]):
            key = "modern-teal"
        elif any(w in pref_lower for w in ["warm", "creative", "colorful"]):
            key = "warm-orange"
        else:
            key = "professional-blue"
        return {"template_name": key, **_AVAILABLE_TEMPLATES[key]}

    # Default
    return {"template_name": "professional-blue", **_AVAILABLE_TEMPLATES["professional-blue"]}


@register
def list_templates() -> dict:
    """List all available PPT templates with descriptions."""
    return {
        "templates": [
            {"name": key, **tmpl} for key, tmpl in _AVAILABLE_TEMPLATES.items()
        ]
    }
