"""RAG — BM25 retrieval, file parsing, chunking, web search, and knowledge management.

Core entry points::

    knowledge_service.ingest                # ingest a file into the knowledge base (DB + BM25 index)
    knowledge_service.search                # BM25 search across all chunks for a user
    knowledge_service.rebuild_user_index    # rebuild a user's BM25 index
    knowledge_service.remove_file           # remove a file from the knowledge base 

    web_search_service.search               # search the web for a query, returning [{title, url, snippet}, ...]
    web_search_service.fetch_and_ingest     # fetch a URL, scrape it, and ingest into the knowledge base (DB + BM25 index)
"""

from .knowledge import KnowledgeService, knowledge_service
from .web_search import WebSearchService, web_search_service

__all__ = [
    "KnowledgeService",
    "knowledge_service",
    "WebSearchService",
    "web_search_service",
]
