"""System endpoints — config, health."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from pptgenius.infrastructure.config import get_settings
from pptgenius.infrastructure.db import Database

from .deps import get_db
from .schemas import ApiResponse, ConfigData, HealthData

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/config")
async def get_config() -> ApiResponse[ConfigData]:
    cfg = get_settings()
    return ApiResponse(data=ConfigData(
        rag={
            "top_k": cfg.rag.top_k,
        },
        agent={
            "outline": {
                "generator_max_retries": cfg.agent.outline.generator_max_retries,
            },
            "cache": {
                "trim_max_tokens": cfg.agent.cache.trim_max_tokens,
                "enable_node_cache": cfg.agent.cache.enable_node_cache,
                "summarize_threshold": cfg.agent.cache.summarize_threshold,
            },
        },
        llm={
            "provider": cfg.llm.provider,
            "model": cfg.llm.model,
        },
        web_search={
            "enabled": cfg.web_search.enabled,
            "engine": cfg.web_search.engine,
            "max_results": cfg.web_search.max_results,
        },
    ))


@router.get("/health")
async def health(db: Database = Depends(get_db)) -> ApiResponse[HealthData]:
    """Health check — verifies DB connectivity, flags LLM and BM25 status."""
    db_ok = "unknown"
    try:
        await db.get_or_create_default_user()
        db_ok = "connected"
    except Exception:
        db_ok = "disconnected"

    # LLM availability is checked lazily (first API call)
    llm_status = "unknown"
    try:
        cfg = get_settings()
        if cfg.llm.api_key and cfg.llm.api_key != "your_deepseek_api_key":
            llm_status = "configured"
        else:
            llm_status = "unconfigured"
    except Exception:
        llm_status = "error"

    # BM25 index existence
    from pathlib import Path
    index_dir = Path(get_settings().workspace.root) / "indexes"
    bm25_status = "ready" if any(index_dir.glob("bm25_index_*.pkl")) else "empty"

    return ApiResponse(data=HealthData(
        status="healthy" if db_ok == "connected" else "degraded",
        db=db_ok,
        llm=llm_status,
        bm25=bm25_status,
    ))
