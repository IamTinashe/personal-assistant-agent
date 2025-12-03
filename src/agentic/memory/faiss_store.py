"""
FAISS-based local vector store implementation.

Provides fast, local vector similarity search using FAISS.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from agentic.core.exceptions import VectorStoreError
from agentic.core.logging import LoggerMixin
from agentic.memory.base import MemoryEntry, MemoryType, SearchResult, VectorStoreBase


class FAISSVectorStore(VectorStoreBase, LoggerMixin):
    """
    Local vector store using FAISS for similarity search.
    
    Features:
    - Fast approximate nearest neighbor search
    - Supports metadata filtering
    - Automatic persistence to disk
    - Memory-efficient for moderate datasets
    
    Args:
        dimension: Vector embedding dimension size.
        store_path: Path to store index and metadata files.
        index_type: FAISS index type (flat, ivf, hnsw).
    """

    def __init__(
        self,
        dimension: int = 1536,
        store_path: Path | str = "./data/vector_store",
        index_type: str = "flat",
    ) -> None:
        self.dimension = dimension
        self.store_path = Path(store_path)
        self.index_type = index_type
        
        self._index: faiss.Index | None = None
        self._metadata: dict[str, dict[str, Any]] = {}
        self._embeddings: dict[str, list[float]] = {}
        self._id_to_idx: dict[str, int] = {}
        self._idx_to_id: dict[int, str] = {}
        self._current_idx: int = 0
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the FAISS index."""
        if self._initialized:
            return
            
        self.store_path.mkdir(parents=True, exist_ok=True)
        
        # Create FAISS index based on type
        if self.index_type == "flat":
            self._index = faiss.IndexFlatIP(self.dimension)  # Inner product for cosine similarity
        elif self.index_type == "ivf":
            quantizer = faiss.IndexFlatIP(self.dimension)
            self._index = faiss.IndexIVFFlat(quantizer, self.dimension, 100)
        elif self.index_type == "hnsw":
            self._index = faiss.IndexHNSWFlat(self.dimension, 32)
        else:
            raise VectorStoreError(f"Unknown index type: {self.index_type}")
        
        # Try to load existing data
        try:
            await self.load()
            self.logger.info(f"Loaded existing vector store with {await self.count()} entries")
        except FileNotFoundError:
            self.logger.info("Created new vector store")
        
        self._initialized = True

    async def add(self, entry: MemoryEntry) -> str:
        """Add a memory entry to the store."""
        self._ensure_initialized()
        
        if entry.embedding is None:
            raise VectorStoreError("Entry must have an embedding")
        
        entry_id = str(entry.id)
        
        # Normalize embedding for cosine similarity
        embedding = np.array([entry.embedding], dtype=np.float32)
        faiss.normalize_L2(embedding)
        
        # Add to FAISS index
        self._index.add(embedding)
        
        # Store metadata and mapping
        self._metadata[entry_id] = entry.to_dict()
        self._embeddings[entry_id] = entry.embedding
        self._id_to_idx[entry_id] = self._current_idx
        self._idx_to_id[self._current_idx] = entry_id
        self._current_idx += 1
        
        self.logger.debug(f"Added memory entry: {entry_id}")
        return entry_id

    async def add_batch(self, entries: list[MemoryEntry]) -> list[str]:
        """Add multiple memory entries in batch."""
        self._ensure_initialized()
        
        if not entries:
            return []
        
        # Validate all entries have embeddings
        for entry in entries:
            if entry.embedding is None:
                raise VectorStoreError(f"Entry {entry.id} must have an embedding")
        
        # Prepare embeddings matrix
        embeddings = np.array(
            [entry.embedding for entry in entries],
            dtype=np.float32,
        )
        faiss.normalize_L2(embeddings)
        
        # Add all to FAISS index
        self._index.add(embeddings)
        
        # Store metadata and mappings
        ids = []
        for entry in entries:
            entry_id = str(entry.id)
            self._metadata[entry_id] = entry.to_dict()
            self._embeddings[entry_id] = entry.embedding
            self._id_to_idx[entry_id] = self._current_idx
            self._idx_to_id[self._current_idx] = entry_id
            self._current_idx += 1
            ids.append(entry_id)
        
        self.logger.debug(f"Added {len(entries)} memory entries in batch")
        return ids

    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> list[SearchResult]:
        """Search for similar memories."""
        self._ensure_initialized()
        
        if self._index.ntotal == 0:
            return []
        
        # Normalize query embedding
        query = np.array([query_embedding], dtype=np.float32)
        faiss.normalize_L2(query)
        
        # Search more results than needed for filtering
        search_k = min(k * 3, self._index.ntotal)
        distances, indices = self._index.search(query, search_k)
        
        results: list[SearchResult] = []
        
        for distance, idx in zip(distances[0], indices[0]):
            if idx == -1:  # FAISS returns -1 for empty slots
                continue
                
            entry_id = self._idx_to_id.get(int(idx))
            if entry_id is None:
                continue
            
            metadata = self._metadata.get(entry_id)
            if metadata is None:
                continue
            
            # Apply filters
            if memory_types:
                if metadata["memory_type"] not in [mt.value for mt in memory_types]:
                    continue
            
            if filter_metadata:
                if not self._matches_filter(metadata.get("metadata", {}), filter_metadata):
                    continue
            
            # Reconstruct entry
            entry = MemoryEntry.from_dict(
                metadata,
                embedding=self._embeddings.get(entry_id),
            )
            
            # Increment access count
            entry.access_count += 1
            self._metadata[entry_id]["access_count"] = entry.access_count
            
            # Score is similarity (0-1 range for normalized vectors with IP)
            score = float(distance)
            
            results.append(SearchResult(
                entry=entry,
                score=score,
                distance=1.0 - score,  # Convert to distance
            ))
            
            if len(results) >= k:
                break
        
        return results

    async def get(self, entry_id: str) -> MemoryEntry | None:
        """Get a specific memory entry by ID."""
        self._ensure_initialized()
        
        metadata = self._metadata.get(entry_id)
        if metadata is None:
            return None
        
        return MemoryEntry.from_dict(
            metadata,
            embedding=self._embeddings.get(entry_id),
        )

    async def update(self, entry: MemoryEntry) -> bool:
        """Update an existing memory entry."""
        self._ensure_initialized()
        
        entry_id = str(entry.id)
        if entry_id not in self._metadata:
            return False
        
        # Update metadata
        entry.updated_at = datetime.utcnow()
        self._metadata[entry_id] = entry.to_dict()
        
        # If embedding changed, we need to rebuild (FAISS doesn't support in-place update)
        if entry.embedding and entry.embedding != self._embeddings.get(entry_id):
            self._embeddings[entry_id] = entry.embedding
            await self._rebuild_index()
        
        self.logger.debug(f"Updated memory entry: {entry_id}")
        return True

    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        self._ensure_initialized()
        
        if entry_id not in self._metadata:
            return False
        
        # Remove from metadata
        del self._metadata[entry_id]
        del self._embeddings[entry_id]
        
        # Remove from mappings
        idx = self._id_to_idx.pop(entry_id, None)
        if idx is not None:
            del self._idx_to_id[idx]
        
        # Rebuild index (FAISS doesn't support deletion)
        await self._rebuild_index()
        
        self.logger.debug(f"Deleted memory entry: {entry_id}")
        return True

    async def clear(self) -> None:
        """Clear all entries from the store."""
        self._ensure_initialized()
        
        self._index.reset()
        self._metadata.clear()
        self._embeddings.clear()
        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._current_idx = 0
        
        self.logger.info("Cleared vector store")

    async def count(self) -> int:
        """Get the total number of entries in the store."""
        return len(self._metadata) if self._initialized else 0

    async def save(self) -> None:
        """Persist the store to disk."""
        self._ensure_initialized()
        
        index_path = self.store_path / "index.faiss"
        metadata_path = self.store_path / "metadata.json"
        embeddings_path = self.store_path / "embeddings.pkl"
        mappings_path = self.store_path / "mappings.pkl"
        
        # Save FAISS index
        faiss.write_index(self._index, str(index_path))
        
        # Save metadata as JSON
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, indent=2)
        
        # Save embeddings and mappings as pickle
        with open(embeddings_path, "wb") as f:
            pickle.dump(self._embeddings, f)
        
        with open(mappings_path, "wb") as f:
            pickle.dump({
                "id_to_idx": self._id_to_idx,
                "idx_to_id": self._idx_to_id,
                "current_idx": self._current_idx,
            }, f)
        
        self.logger.info(f"Saved vector store to {self.store_path}")

    async def load(self) -> None:
        """Load the store from disk."""
        index_path = self.store_path / "index.faiss"
        metadata_path = self.store_path / "metadata.json"
        embeddings_path = self.store_path / "embeddings.pkl"
        mappings_path = self.store_path / "mappings.pkl"
        
        if not all(p.exists() for p in [index_path, metadata_path]):
            raise FileNotFoundError("Vector store files not found")
        
        # Load FAISS index
        self._index = faiss.read_index(str(index_path))
        
        # Load metadata
        with open(metadata_path, encoding="utf-8") as f:
            self._metadata = json.load(f)
        
        # Load embeddings
        if embeddings_path.exists():
            with open(embeddings_path, "rb") as f:
                self._embeddings = pickle.load(f)
        
        # Load mappings
        if mappings_path.exists():
            with open(mappings_path, "rb") as f:
                mappings = pickle.load(f)
                self._id_to_idx = mappings["id_to_idx"]
                self._idx_to_id = {int(k): v for k, v in mappings["idx_to_id"].items()}
                self._current_idx = mappings["current_idx"]

    async def close(self) -> None:
        """Close connections and cleanup resources."""
        if self._initialized:
            await self.save()
            self._initialized = False
            self.logger.info("Closed vector store")

    def _ensure_initialized(self) -> None:
        """Ensure the store is initialized."""
        if not self._initialized:
            raise VectorStoreError("Vector store not initialized. Call initialize() first.")

    def _matches_filter(
        self,
        metadata: dict[str, Any],
        filter_criteria: dict[str, Any],
    ) -> bool:
        """Check if metadata matches filter criteria."""
        for key, value in filter_criteria.items():
            if key not in metadata:
                return False
            if isinstance(value, list):
                if metadata[key] not in value:
                    return False
            elif metadata[key] != value:
                return False
        return True

    async def _rebuild_index(self) -> None:
        """Rebuild the FAISS index from stored embeddings."""
        # Reset index
        self._index.reset()
        
        # Rebuild mappings
        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._current_idx = 0
        
        if not self._embeddings:
            return
        
        # Re-add all embeddings
        for entry_id, embedding in self._embeddings.items():
            emb_array = np.array([embedding], dtype=np.float32)
            faiss.normalize_L2(emb_array)
            self._index.add(emb_array)
            
            self._id_to_idx[entry_id] = self._current_idx
            self._idx_to_id[self._current_idx] = entry_id
            self._current_idx += 1
        
        self.logger.debug("Rebuilt FAISS index")
