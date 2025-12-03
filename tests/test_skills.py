"""
Tests for skills.
"""

import pytest
from datetime import datetime, timedelta

from agentic.preprocessing.preprocessor import InputPreprocessor, IntentType
from agentic.skills.reminder import ReminderSkill
from agentic.skills.tasks import TaskSkill
from agentic.skills.notes import NotesSkill


@pytest.fixture
def preprocessor():
    return InputPreprocessor()


@pytest.fixture
async def reminder_skill(tmp_path):
    skill = ReminderSkill(storage_path=tmp_path / "reminders.json")
    await skill.setup()
    yield skill
    await skill.teardown()


@pytest.fixture
async def task_skill(tmp_path):
    skill = TaskSkill(storage_path=tmp_path / "tasks.json")
    await skill.setup()
    yield skill
    await skill.teardown()


@pytest.fixture
async def notes_skill(tmp_path):
    skill = NotesSkill(storage_path=tmp_path / "notes.json")
    await skill.setup()
    yield skill
    await skill.teardown()


class TestReminderSkill:
    """Test reminder skill."""

    @pytest.mark.asyncio
    async def test_can_handle_reminder(self, reminder_skill, preprocessor):
        preprocessed = preprocessor.preprocess("Remind me to call mom tomorrow")
        assert await reminder_skill.can_handle(preprocessed)

    @pytest.mark.asyncio
    async def test_cannot_handle_unrelated(self, reminder_skill, preprocessor):
        preprocessed = preprocessor.preprocess("What is the weather?")
        assert not await reminder_skill.can_handle(preprocessed)

    @pytest.mark.asyncio
    async def test_create_reminder(self, reminder_skill, preprocessor):
        preprocessed = preprocessor.preprocess("Remind me to call mom tomorrow at 3pm")
        result = await reminder_skill.execute(preprocessed)
        
        assert result.success
        assert "reminder" in result.data
        assert "call mom" in result.message.lower()

    @pytest.mark.asyncio
    async def test_list_reminders(self, reminder_skill, preprocessor):
        # Create a reminder first
        create_input = preprocessor.preprocess("Remind me to exercise tomorrow")
        await reminder_skill.execute(create_input)
        
        # List reminders
        list_input = preprocessor.preprocess("Show my reminders")
        list_input.intent = IntentType.LIST_TASKS
        result = await reminder_skill.execute(list_input)
        
        assert result.success
        assert len(result.data["reminders"]) >= 1


class TestTaskSkill:
    """Test task skill."""

    @pytest.mark.asyncio
    async def test_create_task(self, task_skill, preprocessor):
        preprocessed = preprocessor.preprocess("Add task buy groceries")
        result = await task_skill.execute(preprocessed)
        
        assert result.success
        assert "task" in result.data
        assert "groceries" in result.data["task"]["content"].lower()

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_skill, preprocessor):
        # Create tasks
        await task_skill.execute(preprocessor.preprocess("Add task: item 1"))
        await task_skill.execute(preprocessor.preprocess("Add task: item 2"))
        
        # List tasks
        list_input = preprocessor.preprocess("Show my tasks")
        result = await task_skill.execute(list_input)
        
        assert result.success
        assert len(result.data["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_complete_task(self, task_skill, preprocessor):
        # Create task
        await task_skill.execute(preprocessor.preprocess("Add task: test item"))
        
        # Complete it
        complete_input = preprocessor.preprocess("Complete task 1")
        complete_input.intent = IntentType.COMPLETE_TASK
        result = await task_skill.execute(complete_input)
        
        assert result.success
        assert "complete" in result.message.lower()


class TestNotesSkill:
    """Test notes skill."""

    @pytest.mark.asyncio
    async def test_create_note(self, notes_skill, preprocessor):
        preprocessed = preprocessor.preprocess("Take a note: Important meeting tomorrow")
        result = await notes_skill.execute(preprocessed)
        
        assert result.success
        assert "note" in result.data
        assert "Important meeting" in result.data["note"]["content"]

    @pytest.mark.asyncio
    async def test_search_notes(self, notes_skill, preprocessor):
        # Create notes
        await notes_skill.execute(
            preprocessor.preprocess("Note: Meeting with John about project")
        )
        await notes_skill.execute(
            preprocessor.preprocess("Note: Grocery list for weekend")
        )
        
        # Search
        search_input = preprocessor.preprocess("Find notes about meeting")
        search_input.intent = IntentType.SEARCH_NOTES
        result = await notes_skill.execute(search_input)
        
        assert result.success
        assert len(result.data["notes"]) >= 1
        assert any("meeting" in n["content"].lower() for n in result.data["notes"])
