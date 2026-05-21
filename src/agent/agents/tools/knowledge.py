"""Tools for querying the RAG knowledge base."""

from ...rag.vector_store import create_vector_store
from .registry import register


@register
def query_knowledge_base(query: str, top_k: int = 5) -> dict:
    """Search the RAG knowledge base for relevant text chunks.

    Args:
        query: The search query string.
        top_k: Number of results to return (default 5).

    Returns:
        Dict with 'results' key containing list of (text, score, source).
    """
    store = create_vector_store()
    results = store.similarity_search(query, k=top_k)
    return {
        "results": [
            {"text": text, "score": round(score, 4), "metadata": meta}
            for text, score, meta in results
        ]
    }
