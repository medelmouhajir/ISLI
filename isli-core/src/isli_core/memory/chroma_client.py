import os
import chromadb
from typing import Any, Optional
import structlog

logger = structlog.get_logger()

class ChromaMemoryClient:
    """Wrapper for ChromaDB interactions in ISLI Core."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("CHROMA_DATA_DIR", "/data/vectors")
        # Ensure directory exists
        if not os.path.exists(self.path):
            try:
                os.makedirs(self.path, exist_ok=True)
            except Exception as exc:
                logger.error("chroma.mkdir_failed", path=self.path, error=str(exc))
        
        try:
            self.client = chromadb.PersistentClient(path=self.path)
            logger.info("chroma.client_initialized", path=self.path)
        except Exception as exc:
            logger.error("chroma.init_failed", error=str(exc))
            raise

    def get_collection(self, name: str):
        """Get or create a collection by name."""
        return self.client.get_or_create_collection(name=name)

    async def save_fact(
        self, 
        collection_name: str, 
        fact_id: str, 
        content: str, 
        metadata: Optional[dict[str, Any]] = None, 
        embedding: Optional[list[float]] = None
    ):
        """Save a document/fact to a collection."""
        try:
            collection = self.get_collection(collection_name)
            collection.add(
                ids=[fact_id],
                documents=[content],
                metadatas=[metadata] if metadata else None,
                embeddings=[embedding] if embedding else None
            )
            logger.info("chroma.fact_saved", collection=collection_name, id=fact_id)
        except Exception as exc:
            logger.error("chroma.save_failed", collection=collection_name, error=str(exc))
            raise

    async def search_facts(
        self, 
        collection_name: str, 
        query_text: Optional[str] = None, 
        query_embedding: Optional[list[float]] = None, 
        limit: int = 5, 
        metadata_filter: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Search for facts in a collection."""
        try:
            collection = self.get_collection(collection_name)
            results = collection.query(
                query_texts=[query_text] if query_text else None,
                query_embeddings=[query_embedding] if query_embedding else None,
                n_results=limit,
                where=metadata_filter
            )
            return results
        except Exception as exc:
            logger.error("chroma.search_failed", collection=collection_name, error=str(exc))
            raise

    def delete_collection(self, name: str):
        """Delete a collection."""
        try:
            self.client.delete_collection(name=name)
            logger.info("chroma.collection_deleted", collection=name)
        except Exception as exc:
            logger.error("chroma.delete_failed", collection=name, error=str(exc))
            raise
