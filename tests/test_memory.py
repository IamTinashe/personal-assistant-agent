"""
Tests for the memory system.
"""

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from agentic.memory.base import MemoryEntry, MemoryType, SearchResult
from agentic.memory.faiss_store import FAISSVectorStore


@pytest.fixture
def embedding():
    """Generate a random embedding vector."""
    import random
    return [random.random() for _ in range(1536)]


@pytest.fixture
async def vector_store(tmp_path):
    """Create a temporary vector store."""
    store = FAISSVectorStore(
        dimension=1536,
        store_path=tmp_path / "vector_store",
    )
    await store.initialize()
    yield store
    await store.close()


class TestMemoryEntry:
    """Test MemoryEntry dataclass."""

    def test_create_entry(self, embedding):
        entry = MemoryEntry(
            content="Test content",
            embedding=embedding,
            memory_type=MemoryType.FACT,
        )
        assert entry.content == "Test content"
        assert entry.memory_type == MemoryType.FACT
        assert entry.embedding == embedding

    def test_to_dict(self, embedding):
        entry = MemoryEntry(
            content="Test",
            embedding=embedding,
        )
        data = entry.to_dict()
        assert "id" in data
        assert data["content"] == "Test"
        assert data["memory_type"] == "conversation"

    def test_from_dict(self, embedding):
        original = MemoryEntry(
            content="Test",
            embedding=embedding,
            memory_type=MemoryType.PREFERENCE,
        )
        data = original.to_dict()
        restored = MemoryEntry.from_dict(data, embedding=embedding)
        assert restored.content == original.content
        assert restored.memory_type == original.memory_type


class TestFAISSVectorStore:
    """Test FAISS vector store."""

    @pytest.mark.asyncio
    async def test_add_entry(self, vector_store, embedding):
        entry = MemoryEntry(
            content="Test entry",
            embedding=embedding,
        )
        entry_id = await vector_store.add(entry)
        assert entry_id is not None
        assert await vector_store.count() == 1

    @pytest.mark.asyncio
    async def test_add_batch(self, vector_store, embedding):
        entries = [
            MemoryEntry(content=f"Entry {i}", embedding=embedding)
            for i in range(5)
        ]
        ids = await vector_store.add_batch(entries)
        assert len(ids) == 5
        assert await vector_store.count() == 5

    @pytest.mark.asyncio
    async def test_search(self, vector_store, embedding):
        # Add some entries
        entries = [
            MemoryEntry(content=f"Entry {i}", embedding=embedding)
            for i in range(3)
        ]
        await vector_store.add_batch(entries)

        # Search
        results = await vector_store.search(embedding, k=2)
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)

    @pytest.mark.asyncio
    async def test_get_entry(self, vector_store, embedding):
        entry = MemoryEntry(
            content="Retrievable entry",
            embedding=embedding,
        )
        entry_id = await vector_store.add(entry)

        retrieved = await vector_store.get(entry_id)
        assert retrieved is not None
        assert retrieved.content == "Retrievable entry"

    @pytest.mark.asyncio
    async def test_delete_entry(self, vector_store, embedding):
        entry = MemoryEntry(
            content="To delete",
            embedding=embedding,
        )
        entry_id = await vector_store.add(entry)
        assert await vector_store.count() == 1

        deleted = await vector_store.delete(entry_id)
        assert deleted is True
        assert await vector_store.count() == 0

    @pytest.mark.asyncio
    async def test_clear(self, vector_store, embedding):
        entries = [
            MemoryEntry(content=f"Entry {i}", embedding=embedding)
            for i in range(3)
        ]
        await vector_store.add_batch(entries)
        assert await vector_store.count() == 3

        await vector_store.clear()
        assert await vector_store.count() == 0

    @pytest.mark.asyncio
    async def test_save_and_load(self, vector_store, embedding, tmp_path):
        entry = MemoryEntry(
            content="Persistent entry",
            embedding=embedding,
        )
        await vector_store.add(entry)
        await vector_store.save()

        # Create new store and load
        new_store = FAISSVectorStore(
            dimension=1536,
            store_path=tmp_path / "vector_store",
        )
        await new_store.initialize()

        assert await new_store.count() == 1
        await new_store.close()

    @pytest.mark.asyncio
    async def test_search_with_memory_type_filter(self, vector_store, embedding):
        # Add entries with different types
        fact = MemoryEntry(
            content="A fact",
            embedding=embedding,
            memory_type=MemoryType.FACT,
        )
        pref = MemoryEntry(
            content="A preference",
            embedding=embedding,
            memory_type=MemoryType.PREFERENCE,
        )
        await vector_store.add(fact)
        await vector_store.add(pref)

        # Search for facts only
        results = await vector_store.search(
            embedding,
            k=10,
            memory_types=[MemoryType.FACT],
        )
        assert len(results) == 1
        assert results[0].entry.memory_type == MemoryType.FACT
