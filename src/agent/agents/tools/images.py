"""Tool for selecting images (built-in library → web search fallback)."""

from pathlib import Path

from .registry import register
from ...config import config

# Built-in preset images descriptions
_PRESET_SUBJECTS = {
    "technology": ["circuit", "code", "data", "network", "robot"],
    "business": ["chart", "handshake", "meeting", "presentation", "growth"],
    "education": ["book", "graduation", "learning", "school", "knowledge"],
    "nature": ["mountain", "ocean", "forest", "sky", "flower"],
    "health": ["heart", "medical", "exercise", "nutrition", "wellness"],
}


@register
def select_image(topic: str, style: str = "icon") -> dict:
    """Find an image suitable for a slide on the given topic.

    Checks the built-in preset library first, then falls back to web search.

    Args:
        topic: The subject to find an image for.
        style: Image style - "icon" for simple icons or "photo" for photographs.

    Returns:
        Dict with image_path, source (preset/web), and alt_text.
    """
    # Check preset library
    topic_lower = topic.lower()
    for category, keywords in _PRESET_SUBJECTS.items():
        if any(kw in topic_lower for kw in keywords) or category in topic_lower:
            return {
                "image_path": f"preset://{category}/{keywords[0]}",
                "source": "preset",
                "alt_text": f"{category} related image",
                "note": "Preset images are placeholders. "
                        "Use actual paths or web search for real images.",
            }

    # Web search fallback
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(topic, max_results=3))
            if results:
                return {
                    "image_path": results[0].get("image", ""),
                    "source": "duckduckgo",
                    "alt_text": topic,
                    "thumbnail": results[0].get("thumbnail", ""),
                }
    except Exception:
        pass

    # Final fallback
    return {
        "image_path": "preset://default/placeholder",
        "source": "preset",
        "alt_text": topic,
        "note": "No suitable image found. Using placeholder.",
    }
