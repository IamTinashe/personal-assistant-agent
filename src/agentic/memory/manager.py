"""
Memory manager that coordinates vector store operations and context retrieval.

Provides a high-level interface for storing and retrieving memories.
"""

from datetime import datetime, timedelta
from typing import Any

from agentic.core.config import Settings, VectorStoreType
from agentic.core.exceptions import MemoryError
from agentic.core.logging import LoggerMixin
from agentic.memory.base import MemoryEntry, MemoryType, SearchResult, VectorStoreBase
from agentic.memory.faiss_store import FAISSVectorStore


class MemoryManager(LoggerMixin):
    """
    High-level memory management for the assistant.
    
    Handles:
    - Storing conversation history
    - Retrieving relevant context for prompts
    - Managing personal facts and preferences
    - Memory consolidation and cleanup
    
    Args:
        settings: Application settings.
        embedding_generator: Async function to generate embeddings.
    """

    def __init__(
        self,
        settings: Settings,
        embedding_generator: Any,  # Callable[[str], Awaitable[list[float]]]
    ) -> None:
        self.settings = settings
        self._generate_embedding = embedding_generator
        self._store: VectorStoreBase | None = None
        self._conversation_buffer: list[dict[str, str]] = []
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the memory manager and vector store."""
        if self._initialized:
            return
        
        try:
            if self.settings.vector_store_type == VectorStoreType.FAISS:
                self._store = FAISSVectorStore(
                    dimension=self.settings.vector_dimension,
                    store_path=self.settings.vector_store_path,
                )
            elif self.settings.vector_store_type == VectorStoreType.PINECONE:
                from agentic.memory.pinecone_store import PineconeVectorStore
                
                if not self.settings.pinecone_api_key:
                    raise MemoryError("Pinecone API key not configured")
                
                self._store = PineconeVectorStore(
                    api_key=self.settings.pinecone_api_key.get_secret_value(),
                    environment=self.settings.pinecone_environment,
                    index_name=self.settings.pinecone_index_name,
                    dimension=self.settings.vector_dimension,
                )
            else:
                raise MemoryError(f"Unknown vector store type: {self.settings.vector_store_type}")
            
            await self._store.initialize()
            self._initialized = True
            self.logger.info(f"Memory manager initialized with {self.settings.vector_store_type.value}")
        except Exception as e:
            raise MemoryError(f"Failed to initialize memory manager: {e}")

    async def store_conversation(
        self,
        user_message: str,
        assistant_response: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a conversation exchange in memory.
        
        Args:
            user_message: The user's message.
            assistant_response: The assistant's response.
            metadata: Optional metadata (e.g., session_id, topic).
            
        Returns:
            str: The ID of the stored memory entry.
        """
        self._ensure_initialized()
        
        # Format conversation for embedding
        content = f"User: {user_message}\nAssistant: {assistant_response}"
        
        # Generate embedding
        embedding = await self._generate_embedding(content)
        
        # Create memory entry
        entry = MemoryEntry(
            content=content,
            embedding=embedding,
            memory_type=MemoryType.CONVERSATION,
            metadata={
                "user_message": user_message,
                "assistant_response": assistant_response,
                **(metadata or {}),
            },
        )
        
        # Add to buffer for recent context
        self._conversation_buffer.append({
            "role": "user",
            "content": user_message,
        })
        self._conversation_buffer.append({
            "role": "assistant",
            "content": assistant_response,
        })
        
        # Trim buffer to max length
        max_messages = self.settings.conversation_history_length * 2
        if len(self._conversation_buffer) > max_messages:
            self._conversation_buffer = self._conversation_buffer[-max_messages:]
        
        # Store in vector store
        return await self._store.add(entry)

    async def store_fact(
        self,
        fact: str,
        importance: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a personal fact in memory.
        
        Args:
            fact: The fact to store (e.g., "User's daughter is named Sarah").
            importance: Importance score (0.0 to 1.0).
            metadata: Optional metadata.
            
        Returns:
            str: The ID of the stored memory entry.
        """
        self._ensure_initialized()
        
        embedding = await self._generate_embedding(fact)
        
        entry = MemoryEntry(
            content=fact,
            embedding=embedding,
            memory_type=MemoryType.FACT,
            importance=importance,
            metadata=metadata or {},
        )
        
        return await self._store.add(entry)

    async def store_preference(
        self,
        preference: str,
        category: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a user preference.
        
        Args:
            preference: The preference (e.g., "Prefers morning reminders").
            category: Optional category (e.g., "communication", "schedule").
            metadata: Optional metadata.
            
        Returns:
            str: The ID of the stored memory entry.
        """
        self._ensure_initialized()
        
        embedding = await self._generate_embedding(preference)
        
        entry = MemoryEntry(
            content=preference,
            embedding=embedding,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,  # Preferences are generally important
            metadata={
                "category": category,
                **(metadata or {}),
            },
        )
        
        return await self._store.add(entry)

    async def store_note(
        self,
        note: str,
        title: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Store a user note.
        
        Args:
            note: The note content.
            title: Optional note title.
            tags: Optional tags for categorization.
            metadata: Optional metadata.
            
        Returns:
            str: The ID of the stored memory entry.
        """
        self._ensure_initialized()
        
        content = f"{title}: {note}" if title else note
        embedding = await self._generate_embedding(content)
        
        entry = MemoryEntry(
            content=note,
            embedding=embedding,
            memory_type=MemoryType.NOTE,
            metadata={
                "title": title,
                "tags": tags or [],
                **(metadata or {}),
            },
        )
        
        return await self._store.add(entry)

    async def retrieve_context(
        self,
        query: str,
        k: int | None = None,
        memory_types: list[MemoryType] | None = None,
        include_recent_conversation: bool = True,
    ) -> str:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The query to find relevant context for.
            k: Number of memories to retrieve (default from settings).
            memory_types: Filter by memory types (default: all).
            include_recent_conversation: Include recent conversation buffer.
            
        Returns:
            str: Formatted context string for prompt injection.
        """
        self._ensure_initialized()
        
        k = k or self.settings.memory_retrieval_count
        
        # Search for relevant memories
        query_embedding = await self._generate_embedding(query)
        results = await self._store.search(
            query_embedding=query_embedding,
            k=k,
            memory_types=memory_types,
        )
        
        context_parts = []
        
        # Add relevant memories
        if results:
            context_parts.append("Relevant memories:")
            for i, result in enumerate(results, 1):
                entry = result.entry
                type_label = entry.memory_type.value.capitalize()
                context_parts.append(f"  [{type_label}] {entry.content}")
        
        # Add recent conversation
        if include_recent_conversation and self._conversation_buffer:
            context_parts.append("\nRecent conversation:")
            for msg in self._conversation_buffer[-6:]:  # Last 3 exchanges
                role = msg["role"].capitalize()
                context_parts.append(f"  {role}: {msg['content'][:200]}...")
        
        return "\n".join(context_parts) if context_parts else ""

    async def search_memories(
        self,
        query: str,
        k: int = 10,
        memory_types: list[MemoryType] | None = None,
        filter_metadata: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Search memories with full results.
        
        Args:
            query: Search query.
            k: Number of results.
            memory_types: Filter by types.
            filter_metadata: Metadata filters.
            
        Returns:
            list[SearchResult]: Full search results with scores.
        """
        self._ensure_initialized()
        
        query_embedding = await self._generate_embedding(query)
        return await self._store.search(
            query_embedding=query_embedding,
            k=k,
            memory_types=memory_types,
            filter_metadata=filter_metadata,
        )

    async def get_recent_conversation(self, limit: int | None = None) -> list[dict[str, str]]:
        """Get recent conversation history from buffer."""
        limit = limit or len(self._conversation_buffer)
        return self._conversation_buffer[-limit:]

    async def clear_conversation_buffer(self) -> None:
        """Clear the conversation buffer (for new session)."""
        self._conversation_buffer.clear()
        self.logger.info("Cleared conversation buffer")

    async def consolidate_memories(
        self,
        older_than_days: int = 30,
        min_access_count: int = 0,
    ) -> int:
        """
        Consolidate old, low-importance memories.
        
        Args:
            older_than_days: Process memories older than this.
            min_access_count: Only consider memories accessed less than this.
            
        Returns:
            int: Number of memories consolidated/removed.
        """
        self._ensure_initialized()
        
        # This is a placeholder for memory consolidation logic
        # In a full implementation, you might:
        # 1. Summarize old conversations into facts
        # 2. Remove duplicate or contradicting information
        # 3. Update importance scores based on access patterns
        
        self.logger.info("Memory consolidation not yet implemented")
        return 0

    async def export_memories(
        self,
        memory_types: list[MemoryType] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export memories for backup or analysis.
        
        Args:
            memory_types: Filter by memory types.
            
        Returns:
            list[dict]: List of memory entries as dictionaries.
        """
        self._ensure_initialized()
        
        # Search with high k to get all memories
        # This is inefficient for large stores - a proper implementation
        # would have a list_all method
        dummy_embedding = [0.0] * self.settings.vector_dimension
        results = await self._store.search(
            query_embedding=dummy_embedding,
            k=10000,
            memory_types=memory_types,
        )
        
        return [r.entry.to_dict() for r in results]

    async def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        self._ensure_initialized()
        
        total_count = await self._store.count()
        
        return {
            "total_memories": total_count,
            "conversation_buffer_size": len(self._conversation_buffer),
            "vector_store_type": self.settings.vector_store_type.value,
        }

    async def save(self) -> None:
        """Persist memory to storage."""
        if self._store:
            await self._store.save()
            self.logger.info("Memory saved to storage")

    async def close(self) -> None:
        """Close the memory manager and release resources."""
        if self._store:
            await self._store.close()
            self._initialized = False
            self.logger.info("Memory manager closed")

    def _ensure_initialized(self) -> None:
        """Ensure the manager is initialized."""
        if not self._initialized:
            raise MemoryError(
                "Memory manager not initialized. Call initialize() first."
            )
