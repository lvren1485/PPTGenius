"""RAG — BM25 retrieval, file parsing, chunking, web search, knowledge management.

Core entry points::

    knowledge_service.build_index    # build BM25 once at explore start
    knowledge_service.search         # BM25 across user chunks
    knowledge_service.search_by_conversation  # BM25 within a conversation
    knowledge_service.remove_index   # discard index after explore returns
    knowledge_service.ingest         # parse + chunk + persist
    knowledge_service.remove_file    # delete file + chunks

    web_search_service.search        # search the web → [{title, url, snippet}, ...]
    web_search_service.fetch_and_ingest  # fetch URL, scrape, ingest, summarise
"""

from .knowledge import KnowledgeService, knowledge_service
from .web_search import WebSearchService, web_search_service

__all__ = [
    "KnowledgeService",
    "knowledge_service",
    "WebSearchService",
    "web_search_service",
]
