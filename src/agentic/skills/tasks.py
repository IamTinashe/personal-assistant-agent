"""
Task skill for managing to-do items and tasks.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from agentic.core.logging import LoggerMixin
from agentic.preprocessing.preprocessor import IntentType, PreprocessedInput
from agentic.skills.base import BaseSkill, SkillResult


class TaskSkill(BaseSkill, LoggerMixin):
    """
    Skill for creating and managing tasks/to-dos.
    
    Features:
    - Create tasks with optional due dates
    - List tasks (all, pending, completed)
    - Mark tasks as complete
    - Delete tasks
    - Priority support
    
    Args:
        storage_path: Path to store tasks (JSON file).
    """

    def __init__(self, storage_path: Path | str = "./data/tasks.json") -> None:
        self._storage_path = Path(storage_path)
        self._tasks: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "tasks"

    @property
    def description(self) -> str:
        return "Create, list, and manage to-do tasks"

    @property
    def supported_intents(self) -> list[IntentType]:
        return [
            IntentType.CREATE_TASK,
            IntentType.LIST_TASKS,
            IntentType.COMPLETE_TASK,
            IntentType.DELETE_TASK,
        ]

    async def setup(self) -> None:
        """Load existing tasks from storage."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        if self._storage_path.exists():
            try:
                with open(self._storage_path, encoding="utf-8") as f:
                    self._tasks = json.load(f)
                self.logger.info(f"Loaded {len(self._tasks)} tasks")
            except Exception as e:
                self.logger.warning(f"Failed to load tasks: {e}")
                self._tasks = []

    async def teardown(self) -> None:
        """Save tasks to storage."""
        await self._save()

    async def can_handle(self, preprocessed: PreprocessedInput) -> bool:
        """Check if this skill can handle the input."""
        if preprocessed.intent in self.supported_intents:
            return True
        
        text_lower = preprocessed.cleaned_text.lower()
        task_keywords = ["task", "to-do", "todo", "add to list"]
        return any(kw in text_lower for kw in task_keywords)

    async def execute(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Execute the task skill."""
        intent = preprocessed.intent
        
        if intent == IntentType.CREATE_TASK:
            return await self._create_task(preprocessed)
        elif intent == IntentType.LIST_TASKS:
            return await self._list_tasks(preprocessed)
        elif intent == IntentType.COMPLETE_TASK:
            return await self._complete_task(preprocessed)
        elif intent == IntentType.DELETE_TASK:
            return await self._delete_task(preprocessed)
        
        # Default based on content
        return await self._create_task(preprocessed)

    async def _create_task(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Create a new task."""
        content = preprocessed.cleaned_text
        
        # Clean up common phrases
        for phrase in [
            "add task", "create task", "add to my list",
            "add to to-do", "add to todo", "i need to"
        ]:
            content = content.replace(phrase, "").strip()
        
        # Check for quoted content
        quoted = preprocessed.get_entity("quoted_text")
        if quoted:
            content = quoted.value
        
        if not content:
            return SkillResult(
                success=False,
                message="What task would you like me to add?",
                should_respond=True,
            )
        
        # Check for due date
        due_date = None
        datetime_entity = preprocessed.get_entity("datetime")
        if datetime_entity:
            due_date = datetime_entity.value.isoformat()
            content = content.replace(datetime_entity.raw_text, "").strip()
        
        # Detect priority from keywords
        priority = "normal"
        if any(word in content.lower() for word in ["urgent", "asap", "important"]):
            priority = "high"
        elif any(word in content.lower() for word in ["sometime", "eventually", "later"]):
            priority = "low"
        
        # Create task
        task = {
            "id": str(uuid4()),
            "content": content,
            "completed": False,
            "priority": priority,
            "due_date": due_date,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        }
        
        self._tasks.append(task)
        await self._save()
        
        self.logger.info(f"Created task: {content}")
        
        message = f"Added to your to-do list: \"{content}\""
        if due_date:
            due_str = datetime.fromisoformat(due_date).strftime("%b %d")
            message += f" (due {due_str})"
        
        return SkillResult(
            success=True,
            message=message,
            data={"task": task},
            should_respond=True,
        )

    async def _list_tasks(self, preprocessed: PreprocessedInput) -> SkillResult:
        """List tasks."""
        text_lower = preprocessed.cleaned_text.lower()
        
        # Determine filter
        show_completed = "completed" in text_lower or "done" in text_lower
        show_all = "all" in text_lower
        
        if show_all:
            tasks = self._tasks
        elif show_completed:
            tasks = [t for t in self._tasks if t.get("completed")]
        else:
            tasks = [t for t in self._tasks if not t.get("completed")]
        
        if not tasks:
            if show_completed:
                return SkillResult(
                    success=True,
                    message="You haven't completed any tasks yet.",
                    data={"tasks": []},
                )
            return SkillResult(
                success=True,
                message="Your to-do list is empty! 🎉",
                data={"tasks": []},
            )
        
        # Sort by priority and due date
        priority_order = {"high": 0, "normal": 1, "low": 2}
        tasks.sort(key=lambda t: (
            priority_order.get(t.get("priority", "normal"), 1),
            t.get("due_date") or "9999",
        ))
        
        lines = [f"You have {len(tasks)} task(s):"]
        for i, task in enumerate(tasks, 1):
            status = "✓" if task.get("completed") else "○"
            priority_icon = "🔴" if task.get("priority") == "high" else ""
            
            line = f"{status} {i}. {task['content']}"
            if priority_icon:
                line = f"{status} {i}. {priority_icon} {task['content']}"
            
            if task.get("due_date"):
                due = datetime.fromisoformat(task["due_date"]).strftime("%b %d")
                line += f" (due {due})"
            
            lines.append(line)
        
        return SkillResult(
            success=True,
            message="\n".join(lines),
            data={"tasks": tasks},
        )

    async def _complete_task(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Mark a task as complete."""
        # Try to find task by number
        number_entity = preprocessed.get_entity("number")
        pending_tasks = [t for t in self._tasks if not t.get("completed")]
        
        if number_entity:
            idx = int(number_entity.value) - 1
            if 0 <= idx < len(pending_tasks):
                task = pending_tasks[idx]
                task["completed"] = True
                task["completed_at"] = datetime.now().isoformat()
                await self._save()
                
                return SkillResult(
                    success=True,
                    message=f"Great job! Marked \"{task['content']}\" as complete. ✓",
                    data={"task": task},
                )
        
        # Try to find by content match
        text_lower = preprocessed.cleaned_text.lower()
        for task in pending_tasks:
            if task["content"].lower() in text_lower:
                task["completed"] = True
                task["completed_at"] = datetime.now().isoformat()
                await self._save()
                
                return SkillResult(
                    success=True,
                    message=f"Great job! Marked \"{task['content']}\" as complete. ✓",
                    data={"task": task},
                )
        
        return SkillResult(
            success=False,
            message="I couldn't find that task. Try listing your tasks first with 'show my tasks'.",
        )

    async def _delete_task(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Delete a task."""
        number_entity = preprocessed.get_entity("number")
        
        if number_entity:
            idx = int(number_entity.value) - 1
            if 0 <= idx < len(self._tasks):
                task = self._tasks.pop(idx)
                await self._save()
                
                return SkillResult(
                    success=True,
                    message=f"Deleted task: \"{task['content']}\"",
                    data={"task": task},
                )
        
        return SkillResult(
            success=False,
            message="I couldn't find that task. Use task number from the list.",
        )

    async def _save(self) -> None:
        """Save tasks to storage."""
        try:
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump(self._tasks, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save tasks: {e}")
