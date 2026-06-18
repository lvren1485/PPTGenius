"""RAG — BM25 retrieval, file parsing, chunking, web search, knowledge management.

Core entry points::

    knowledge_service.ingest                # ingest a file (DB + dirty-flag)
    knowledge_service.search                # BM25 across all chunks for a user (dynamic index)
    knowledge_service.search_by_conversation # BM25 within a conversation (dynamic index)
    knowledge_service.remove_file           # remove a file + mark index dirty

    web_search_service.search               # search the web → [{title, url, snippet}, ...]
    web_search_service.fetch_and_ingest     # fetch URL, scrape, ingest, summarise
"""

from .knowledge import KnowledgeService, knowledge_service
from .web_search import WebSearchService, web_search_service

__all__ = [
    "KnowledgeService",
    "knowledge_service",
    "WebSearchService",
    "web_search_service",
]
