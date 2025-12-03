"""
Notes skill for creating and searching notes.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic.core.logging import LoggerMixin
from agentic.preprocessing.preprocessor import IntentType, PreprocessedInput
from agentic.skills.base import BaseSkill, SkillResult


class NotesSkill(BaseSkill, LoggerMixin):
    """
    Skill for creating and managing notes.
    
    Features:
    - Create notes with optional titles and tags
    - Search notes by content
    - List recent notes
    - Delete notes
    
    Args:
        storage_path: Path to store notes (JSON file).
    """

    def __init__(self, storage_path: Path | str = "./data/notes.json") -> None:
        self._storage_path = Path(storage_path)
        self._notes: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "notes"

    @property
    def description(self) -> str:
        return "Create, search, and manage personal notes"

    @property
    def supported_intents(self) -> list[IntentType]:
        return [IntentType.CREATE_NOTE, IntentType.SEARCH_NOTES]

    async def setup(self) -> None:
        """Load existing notes from storage."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self._storage_path.exists():
            try:
                with open(self._storage_path, encoding="utf-8") as f:
                    self._notes = json.load(f)
                self.logger.info(f"Loaded {len(self._notes)} notes")
            except Exception as e:
                self.logger.warning(f"Failed to load notes: {e}")
                self._notes = []

    async def teardown(self) -> None:
        """Save notes to storage."""
        await self._save()

    async def can_handle(self, preprocessed: PreprocessedInput) -> bool:
        """Check if this skill can handle the input."""
        if preprocessed.intent in [IntentType.CREATE_NOTE, IntentType.SEARCH_NOTES]:
            return True
        
        text_lower = preprocessed.cleaned_text.lower()
        note_keywords = ["note", "write down", "jot down", "remember that"]
        return any(kw in text_lower for kw in note_keywords)

    async def execute(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Execute the notes skill."""
        intent = preprocessed.intent
        
        if intent == IntentType.CREATE_NOTE:
            return await self._create_note(preprocessed)
        elif intent == IntentType.SEARCH_NOTES:
            return await self._search_notes(preprocessed)
        
        # Default to creating a note
        return await self._create_note(preprocessed)

    async def _create_note(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Create a new note."""
        content = preprocessed.cleaned_text
        
        # Clean up common phrases
        for phrase in [
            "take a note", "make a note", "note that", "write down",
            "jot down", "remember that", "note:"
        ]:
            content = content.replace(phrase, "").strip()
        
        # Check for quoted content
        quoted = preprocessed.get_entity("quoted_text")
        if quoted:
            content = quoted.value
        
        if not content:
            return SkillResult(
                success=False,
                message="What would you like me to note down?",
                should_respond=True,
            )
        
        # Extract potential title (first sentence or first few words)
        title = content.split(".")[0][:50] if "." in content else content[:50]
        if len(title) == 50:
            title = title.rsplit(" ", 1)[0] + "..."
        
        # Create note
        note = {
            "id": str(uuid4()),
            "title": title,
            "content": content,
            "tags": [],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        self._notes.append(note)
        await self._save()
        
        self.logger.info(f"Created note: {title}")
        
        return SkillResult(
            success=True,
            message=f"I've saved your note: \"{title}\"",
            data={"note": note},
            should_respond=True,
        )

    async def _search_notes(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Search notes by content."""
        query = preprocessed.cleaned_text.lower()
        
        # Clean up common search phrases
        for phrase in [
            "find note", "search notes", "look for note",
            "what did i write about", "find my note about"
        ]:
            query = query.replace(phrase, "").strip()
        
        if not query:
            # Return recent notes
            recent = self._notes[-5:][::-1]  # Last 5, newest first
            if not recent:
                return SkillResult(
                    success=True,
                    message="You don't have any notes yet.",
                    data={"notes": []},
                )
            
            lines = ["Here are your recent notes:"]
            for i, note in enumerate(recent, 1):
                date = datetime.fromisoformat(note["created_at"]).strftime("%b %d")
                lines.append(f"{i}. [{date}] {note['title']}")
            
            return SkillResult(
                success=True,
                message="\n".join(lines),
                data={"notes": recent},
            )
        
        # Search notes
        matches = []
        for note in self._notes:
            if (
                query in note["content"].lower()
                or query in note["title"].lower()
                or any(query in tag.lower() for tag in note.get("tags", []))
            ):
                matches.append(note)
        
        if not matches:
            return SkillResult(
                success=True,
                message=f"I couldn't find any notes matching '{query}'.",
                data={"notes": []},
            )
        
        lines = [f"Found {len(matches)} note(s) matching '{query}':"]
        for i, note in enumerate(matches[:5], 1):  # Show top 5
            date = datetime.fromisoformat(note["created_at"]).strftime("%b %d")
            preview = note["content"][:100]
            if len(note["content"]) > 100:
                preview += "..."
            lines.append(f"{i}. [{date}] {note['title']}")
            lines.append(f"   {preview}")
        
        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"notes": matches},
        )

    async def _save(self) -> None:
        """Save notes to storage."""
        try:
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._notes, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save notes: {e}")
