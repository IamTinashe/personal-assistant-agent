"""
Reminder skill for creating and managing reminders.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic.core.logging import LoggerMixin
from agentic.preprocessing.preprocessor import IntentType, PreprocessedInput
from agentic.skills.base import BaseSkill, SkillResult


class ReminderSkill(BaseSkill, LoggerMixin):
    """
    Skill for creating and managing reminders.
    
    Features:
    - Create reminders with natural language time parsing
    - List upcoming reminders
    - Delete/complete reminders
    - Persistent storage
    
    Args:
        storage_path: Path to store reminders (JSON file).
    """

    def __init__(self, storage_path: Path | str = "./data/reminders.json") -> None:
        self._storage_path = Path(storage_path)
        self._reminders: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "reminder"

    @property
    def description(self) -> str:
        return "Create, list, and manage reminders with natural language time parsing"

    @property
    def supported_intents(self) -> list[IntentType]:
        return [IntentType.SET_REMINDER, IntentType.LIST_TASKS, IntentType.DELETE_TASK]

    async def setup(self) -> None:
        """Load existing reminders from storage."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self._storage_path.exists():
            try:
                with open(self._storage_path, encoding="utf-8") as f:
                    self._reminders = json.load(f)
                self.logger.info(f"Loaded {len(self._reminders)} reminders")
            except Exception as e:
                self.logger.warning(f"Failed to load reminders: {e}")
                self._reminders = []

    async def teardown(self) -> None:
        """Save reminders to storage."""
        await self._save()

    async def can_handle(self, preprocessed: PreprocessedInput) -> bool:
        """Check if this skill can handle the input."""
        if preprocessed.intent == IntentType.SET_REMINDER:
            return True
        
        # Check for reminder-related keywords
        text_lower = preprocessed.cleaned_text.lower()
        reminder_keywords = ["reminder", "remind me", "don't forget"]
        return any(kw in text_lower for kw in reminder_keywords)

    async def execute(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Execute the reminder skill."""
        intent = preprocessed.intent
        
        if intent == IntentType.SET_REMINDER:
            return await self._create_reminder(preprocessed)
        elif intent == IntentType.LIST_TASKS:
            return await self._list_reminders()
        elif intent == IntentType.DELETE_TASK:
            return await self._delete_reminder(preprocessed)
        
        # Default to creating a reminder
        return await self._create_reminder(preprocessed)

    async def _create_reminder(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Create a new reminder."""
        # Extract datetime from entities
        datetime_entity = preprocessed.get_entity("datetime")
        
        if not datetime_entity:
            return SkillResult(
                success=False,
                message="I couldn't understand when you want to be reminded. "
                        "Please specify a time like 'tomorrow at 3pm' or 'in 2 hours'.",
                should_respond=True,
            )
        
        reminder_time: datetime = datetime_entity.value
        
        # Extract reminder content (what to remind about)
        # Remove time-related parts from the message
        content = preprocessed.cleaned_text
        content = content.replace(datetime_entity.raw_text, "").strip()
        
        # Clean up common phrases
        for phrase in ["remind me to", "remind me", "set a reminder to", "set reminder"]:
            content = content.replace(phrase, "").strip()
        
        if not content:
            content = "Reminder"
        
        # Create reminder
        reminder = {
            "id": str(uuid4()),
            "content": content,
            "remind_at": reminder_time.isoformat(),
            "created_at": datetime.now().isoformat(),
            "completed": False,
        }
        
        self._reminders.append(reminder)
        await self._save()
        
        # Format time for response
        time_str = reminder_time.strftime("%A, %B %d at %I:%M %p")
        
        self.logger.info(f"Created reminder: {content} at {time_str}")
        
        return SkillResult(
            success=True,
            message=f"I'll remind you to {content} on {time_str}.",
            data={"reminder": reminder},
            should_respond=True,
            response_hint=f"Confirm the reminder was set for {time_str}",
        )

    async def _list_reminders(self) -> SkillResult:
        """List all active reminders."""
        active_reminders = [r for r in self._reminders if not r.get("completed", False)]
        
        if not active_reminders:
            return SkillResult(
                success=True,
                message="You don't have any active reminders.",
                data={"reminders": []},
            )
        
        # Sort by reminder time
        active_reminders.sort(key=lambda r: r["remind_at"])
        
        # Format for display
        lines = ["Here are your upcoming reminders:"]
        for i, reminder in enumerate(active_reminders, 1):
            time = datetime.fromisoformat(reminder["remind_at"])
            time_str = time.strftime("%b %d at %I:%M %p")
            lines.append(f"{i}. {reminder['content']} - {time_str}")
        
        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"reminders": active_reminders},
        )

    async def _delete_reminder(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Delete or complete a reminder."""
        # Try to find reminder by number or content
        number_entity = preprocessed.get_entity("number")
        
        if number_entity:
            idx = int(number_entity.value) - 1
            active_reminders = [r for r in self._reminders if not r.get("completed", False)]
            
            if 0 <= idx < len(active_reminders):
                reminder = active_reminders[idx]
                reminder["completed"] = True
                await self._save()
                
                return SkillResult(
                    success=True,
                    message=f"Marked reminder '{reminder['content']}' as complete.",
                    data={"reminder": reminder},
                )
        
        return SkillResult(
            success=False,
            message="I couldn't find that reminder. Try listing your reminders first.",
        )

    async def _save(self) -> None:
        """Save reminders to storage."""
        try:
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._reminders, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save reminders: {e}")

    async def get_due_reminders(self) -> list[dict[str, Any]]:
        """Get reminders that are due now."""
        now = datetime.now()
        due = []
        
        for reminder in self._reminders:
            if reminder.get("completed"):
                continue
            
            remind_at = datetime.fromisoformat(reminder["remind_at"])
            if remind_at <= now:
                due.append(reminder)
        
        return due
