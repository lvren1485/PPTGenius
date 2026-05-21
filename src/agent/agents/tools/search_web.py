"""Tool for web searching via DuckDuckGo (free, no API key required)."""

from .registry import register


@register
def search_web(query: str, max_results: int = 5) -> dict:
    """Search the web for current information on a topic.

    Uses DuckDuckGo search - no API key required.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return (default 5).

    Returns:
        Dict with 'results' key containing list of {title, snippet, url}.
    """
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return {
            "results": [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
                for r in results
            ]
        }
    except ImportError:
        return {"error": "duckduckgo_search not installed"}
    except Exception as e:
        return {"error": f"Search failed: {e}", "results": []}
