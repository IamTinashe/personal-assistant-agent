"""
Base vector store interface and types.

Defines the abstract interface for all vector store implementations.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class MemoryType(str, Enum):
    """Types of memories that can be stored."""

    CONVERSATION = "conversation"
    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    NOTE = "note"
    CONTEXT = "context"


@dataclass
class MemoryEntry:
    """
    Represents a single memory entry in the vector store.
    
    Attributes:
        id: Unique identifier for the memory.
        content: The text content of the memory.
        embedding: Vector embedding of the content.
        memory_type: Classification of the memory.
        metadata: Additional metadata for filtering and context.
        created_at: Timestamp when the memory was created.
        updated_at: Timestamp when the memory was last updated.
        importance: Importance score (0.0 to 1.0) for prioritization.
        access_count: Number of times this memory was retrieved.
    """

    content: str
    memory_type: MemoryType = MemoryType.CONVERSATION
    id: UUID = field(default_factory=uuid4)
    embedding: list[float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    importance: float = 0.5
    access_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": str(self.id),
            "content": self.content,
            "memory_type": self.memory_type.value,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "importance": self.importance,
            "access_count": self.access_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], embedding: list[float] | None = None) -> "MemoryEntry":
        """Create from dictionary."""
        return cls(
            id=UUID(data["id"]),
            content=data["content"],
            embedding=embedding,
            memory_type=MemoryType(data["memory_type"]),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
        )


@dataclass
class SearchResult:
    """
    Result from a vector similarity search.
    
    Attributes:
        entry: The matched memory entry.
        score: Similarity score (higher is more similar).
        distance: Distance metric (lower is more similar).
    """

    entry: MemoryEntry
    score: float
    distance: float


class VectorStoreBase(ABC):
    """
    Abstract base class for vector store implementations.
    
    Provides a consistent interface for different vector databases.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the vector store connection/resources."""
        pass

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> str:
        """
        Add a memory entry to the store.
        
        Args:
            entry: The memory entry to add.
            
        Returns:
            str: The ID of the added entry.
        """
        pass

    @abstractmethod
    async def add_batch(self, entries: list[MemoryEntry]) -> list[str]:
        """
        Add multiple memory entries in batch.
        
        Args:
            entries: List of memory entries to add.
            
        Returns:
            list[str]: List of IDs for added entries.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
        memory_types: list[MemoryType] | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar memories.
        
        Args:
            query_embedding: The query vector.
            k: Number of results to return.
            filter_metadata: Optional metadata filters.
            memory_types: Optional filter by memory types.
            
        Returns:
            list[SearchResult]: Ranked search results.
        """
        pass

    @abstractmethod
    async def get(self, entry_id: str) -> MemoryEntry | None:
        """
        Get a specific memory entry by ID.
        
        Args:
            entry_id: The ID of the entry to retrieve.
            
        Returns:
            MemoryEntry | None: The entry if found, None otherwise.
        """
        pass

    @abstractmethod
    async def update(self, entry: MemoryEntry) -> bool:
        """
        Update an existing memory entry.
        
        Args:
            entry: The entry with updated data.
            
        Returns:
            bool: True if updated successfully.
        """
        pass

    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """
        Delete a memory entry.
        
        Args:
            entry_id: The ID of the entry to delete.
            
        Returns:
            bool: True if deleted successfully.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from the store."""
        pass

    @abstractmethod
    async def count(self) -> int:
        """Get the total number of entries in the store."""
        pass

    @abstractmethod
    async def save(self) -> None:
        """Persist the store to disk (if applicable)."""
        pass

    @abstractmethod
    async def load(self) -> None:
        """Load the store from disk (if applicable)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connections and cleanup resources."""
        pass
