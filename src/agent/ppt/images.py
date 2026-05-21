"""Image sourcing and embedding for slides.

Built-in library uses placeholder shapes. Web search fallback via DuckDuckGo.
"""


_PRESET_KEYWORDS = {
    "technology": ["circuit", "code", "data", "network", "robot"],
    "business": ["chart", "handshake", "meeting", "presentation", "growth"],
    "education": ["book", "graduation", "learning", "school", "knowledge"],
    "nature": ["mountain", "ocean", "forest", "sky", "flower"],
    "health": ["heart", "medical", "exercise", "nutrition", "wellness"],
}


def find_image(topic: str) -> dict:
    """Find an image URL/path for a given topic.

    Returns dict with image_path, source.
    """
    topic_lower = topic.lower()
    for category, keywords in _PRESET_KEYWORDS.items():
        if any(kw in topic_lower for kw in keywords) or category in topic_lower:
            return {
                "image_path": f"preset://{category}/{keywords[0]}",
                "source": "preset",
            }

    # Web search fallback
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.images(topic, max_results=1))
            if results:
                return {
                    "image_path": results[0].get("image", ""),
                    "source": "duckduckgo",
                }
    except Exception:
        pass

    return {"image_path": "", "source": "none"}
