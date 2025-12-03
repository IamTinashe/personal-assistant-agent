"""
Pinecone cloud vector store implementation.

Provides scalable cloud-based vector similarity search.
"""

from typing import Any

from agentic.core.exceptions import ConfigurationError, VectorStoreError
from agentic.core.logging import LoggerMixin
from agentic.memory.base import MemoryEntry, MemoryType, SearchResult, VectorStoreBase


class PineconeVectorStore(VectorStoreBase, LoggerMixin):
    """
    Cloud vector store using Pinecone for similarity search.
    
    Features:
    - Scalable cloud infrastructure
    - Managed service with automatic scaling
    - Built-in metadata filtering
    - Real-time updates
    
    Args:
        api_key: Pinecone API key.
        environment: Pinecone environment (e.g., 'us-east-1').
        index_name: Name of the Pinecone index.
        dimension: Vector embedding dimension size.
        namespace: Optional namespace for data isolation.
    """

    def __init__(
        self,
        api_key: str,
        environment: str,
        index_name: str,
        dimension: int = 1536,
        namespace: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.environment = environment
        self.index_name = index_name
        self.dimension = dimension
        self.namespace = namespace or ""
        
        self._index = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize Pinecone connection."""
        if self._initialized:
            return
        
        try:
            import pinecone
        except ImportError:
            raise ConfigurationError(
                "Pinecone client not installed. Install with: pip install pinecone-client"
            )
        
        try:
            pinecone.init(api_key=self.api_key, environment=self.environment)
            
            # Check if index exists
            if self.index_name not in pinecone.list_indexes():
                self.logger.info(f"Creating Pinecone index: {self.index_name}")
                pinecone.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric="cosine",
                )
            
            self._index = pinecone.Index(self.index_name)
            self._initialized = True
            
            stats = self._index.describe_index_stats()
            self.logger.info(
                f"Connected to Pinecone index '{self.index_name}' "
                f"with {stats.total_vector_count} vectors"
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to initialize Pinecone: {e}")

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry to Pinecone."""
        self._ensure_initialized()
        
        if entry.embedding is None:
            raise VectorStoreError("Entry must have an embedding")
        
        entry_id = str(entry.id)
        metadata = entry.to_dict()
        # Pinecone has limits on metadata, remove embedding
        metadata.pop("embedding", None)
        
        try:
            self._index.upsert(
                vectors=[{
                    "id": entry_id,
                    "values": entry.embedding,
                    "metadata": metadata,
                }],
                namespace=self.namespace,
            )
            self.logger.debug(f"Added memory entry to Pinecone: {entry_id}")
            return entry_id
        except Exception as e:
            raise VectorStoreError(f"Failed to add entry to Pinecone: {e}")

    async def add_batch(self, entries: list[MemoryEntry]) -> list[str]:
        """Add multiple memory entries in batch."""
        self._ensure_initialized()
        
        if not entries:
            return []
        
        vectors = []
        ids = []
        
        for entry in entries:
            if entry.embedding is None:
                raise VectorStoreError(f"Entry {entry.id} must have an embedding")
            
            entry_id = str(entry.id)
            metadata = entry.to_dict()
            metadata.pop("embedding", None)
            
            vectors.append({
                "id": entry_id,
                "values": entry.embedding,
                "metadata": metadata,
            })
            ids.append(entry_id)
        
        try:
            # Pinecone recommends batches of 100
            batch_size = 100
            for i in range(0, len(vectors), batch_size):
                batch = vectors[i:i + batch_size]
                self._index.upsert(vectors=batch, namespace=self.namespace)
            
            self.logger.debug(f"Added {len(entries)} entries to Pinecone in batch")
            return ids
        except Exception as e:
            raise VectorStoreError(f"Failed to add batch to Pinecone: {e}")

    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> list[SearchResult]:
        """Search for similar memories in Pinecone."""
        self._ensure_initialized()
        
        # Build Pinecone filter
        pinecone_filter = {}
        
        if memory_types:
            pinecone_filter["memory_type"] = {"$in": [mt.value for mt in memory_types]}
        
        if filter_metadata:
            for key, value in filter_metadata.items():
                if isinstance(value, list):
                    pinecone_filter[f"metadata.{key}"] = {"$in": value}
                else:
                    pinecone_filter[f"metadata.{key}"] = {"$eq": value}
        
        try:
            results = self._index.query(
                vector=query_embedding,
                top_k=k,
                include_metadata=True,
                namespace=self.namespace,
                filter=pinecone_filter if pinecone_filter else None,
            )
            
            search_results = []
            for match in results.matches:
                metadata = match.metadata
                entry = MemoryEntry.from_dict(metadata)
                
                search_results.append(SearchResult(
                    entry=entry,
                    score=match.score,
                    distance=1.0 - match.score,
                ))
            
            return search_results
        except Exception as e:
            raise VectorStoreError(f"Failed to search Pinecone: {e}")

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a specific memory entry by ID."""
        self._ensure_initialized()
        
        try:
            result = self._index.fetch(ids=[entry_id], namespace=self.namespace)
            
            if entry_id not in result.vectors:
                return None
            
            vector = result.vectors[entry_id]
            return MemoryEntry.from_dict(
                vector.metadata,
                embedding=list(vector.values),
            )
        except Exception as e:
            raise VectorStoreError(f"Failed to get entry from Pinecone: {e}")

    async def update(self, entry: MemoryEntry) -> bool:
        """Update an existing memory entry."""
        self._ensure_initialized()
        
        # Pinecone upsert handles both insert and update
        await self.add(entry)
        return True

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        self._ensure_initialized()
        
        try:
            self._index.delete(ids=[entry_id], namespace=self.namespace)
            self.logger.debug(f"Deleted entry from Pinecone: {entry_id}")
            return True
        except Exception as e:
            raise VectorStoreError(f"Failed to delete from Pinecone: {e}")

    async def clear(self) -> None:
        """Clear all entries from the namespace."""
        self._ensure_initialized()
        
        try:
            self._index.delete(delete_all=True, namespace=self.namespace)
            self.logger.info("Cleared Pinecone namespace")
        except Exception as e:
            raise VectorStoreError(f"Failed to clear Pinecone: {e}")

    async def count(self) -> int:
        """Get the total number of entries."""
        self._ensure_initialized()
        
        try:
            stats = self._index.describe_index_stats()
            if self.namespace:
                return stats.namespaces.get(self.namespace, {}).get("vector_count", 0)
            return stats.total_vector_count
        except Exception as e:
            raise VectorStoreError(f"Failed to get count from Pinecone: {e}")

    async def save(self) -> None:
        """No-op for cloud store (data is persisted automatically)."""
        pass

    async def load(self) -> None:
        """No-op for cloud store (data is loaded automatically)."""
        pass

    async def close(self) -> None:
        """Close the Pinecone connection."""
        self._initialized = False
        self.logger.info("Closed Pinecone connection")

    def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if not self._initialized:
            raise VectorStoreError(
                "Pinecone store not initialized. Call initialize() first."
            )
