from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional, List
from uuid import uuid4
import structlog

from isli_core.auth import require_internal_auth
from isli_core.memory.chroma_client import ChromaMemoryClient
from pydantic import BaseModel

logger = structlog.get_logger()
router = APIRouter(prefix="/memory", tags=["memory"])
chroma = ChromaMemoryClient()

class SaveMemoryRequest(BaseModel):
    content: str
    metadata: Optional[dict[str, Any]] = None
    embedding: Optional[List[float]] = None


class DeleteMemoryRequest(BaseModel):
    fact_id: str


@router.post("/delete")
async def delete_memory(
    req: DeleteMemoryRequest,
    auth: dict = Depends(require_internal_auth)
):
    """Delete a fact from the agent's private semantic collection."""
    agent_id = auth["sub"]
    collection_name = f"agent_{agent_id}"
    try:
        await chroma.delete_fact(collection_name=collection_name, fact_id=req.fact_id)
        return {"status": "deleted", "fact_id": req.fact_id, "collection": collection_name}
    except Exception as exc:
        logger.error("router.memory_delete_failed", agent_id=agent_id, fact_id=req.fact_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to delete semantic memory")


@router.post("/save")
async def save_memory(
    req: SaveMemoryRequest,
    auth: dict = Depends(require_internal_auth)
):
    """
    Save a fact to the agent's private semantic collection.
    Agents can ONLY write to their own agent_{id} collection.
    """
    agent_id = auth["sub"]
    collection_name = f"agent_{agent_id}"
    fact_id = str(uuid4())
    
    try:
        await chroma.save_fact(
            collection_name=collection_name,
            fact_id=fact_id,
            content=req.content,
            metadata=req.metadata,
            embedding=req.embedding
        )
        return {"id": fact_id, "collection": collection_name, "status": "saved"}
    except Exception as exc:
        logger.error("router.memory_save_failed", agent_id=agent_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to save semantic memory")

@router.get("/search")
async def search_memory(
    query_text: Optional[str] = None,
    query_embedding: Optional[List[float]] = Query(None),
    collection: str = "global",
    limit: int = 5,
    auth: dict = Depends(require_internal_auth)
):
    """
    Search for facts in a semantic collection.
    Agents can ONLY read from 'global' or their own agent_{id} collection.
    """
    agent_id = auth["sub"]
    
    # Enforce collection scoping rules
    allowed_collections = ["global", f"agent_{agent_id}"]
    if collection not in allowed_collections:
        logger.warning("router.memory_search_denied", agent_id=agent_id, requested_collection=collection)
        raise HTTPException(
            status_code=403,
            detail=f"Access denied to collection: {collection}. You can only search 'global' or your own 'agent:{{id}}' collection."
        )
    
    try:
        results = await chroma.search_facts(
            collection_name=collection,
            query_text=query_text,
            query_embedding=query_embedding,
            limit=limit
        )
        return results
    except Exception as exc:
        logger.error("router.memory_search_failed", agent_id=agent_id, collection=collection, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to search semantic memory")
