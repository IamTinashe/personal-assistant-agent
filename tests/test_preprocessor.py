"""
Tests for input preprocessor.
"""

import pytest
from datetime import datetime, timedelta

from agentic.preprocessing.preprocessor import (
    InputPreprocessor,
    IntentType,
    PreprocessedInput,
)


@pytest.fixture
def preprocessor():
    return InputPreprocessor()


class TestIntentDetection:
    """Test intent detection."""

    def test_set_reminder_intent(self, preprocessor):
        result = preprocessor.preprocess("Remind me to call mom tomorrow")
        assert result.intent == IntentType.SET_REMINDER

    def test_create_task_intent(self, preprocessor):
        result = preprocessor.preprocess("Add task to buy groceries")
        assert result.intent == IntentType.CREATE_TASK

    def test_list_tasks_intent(self, preprocessor):
        result = preprocessor.preprocess("Show my tasks")
        assert result.intent == IntentType.LIST_TASKS

    def test_create_note_intent(self, preprocessor):
        result = preprocessor.preprocess("Take a note: meeting at 3pm")
        assert result.intent == IntentType.CREATE_NOTE

    def test_greeting_intent(self, preprocessor):
        result = preprocessor.preprocess("Hello!")
        assert result.intent == IntentType.GREETING

    def test_question_intent(self, preprocessor):
        result = preprocessor.preprocess("What is the capital of France?")
        assert result.intent == IntentType.QUESTION

    def test_general_intent(self, preprocessor):
        result = preprocessor.preprocess("random text without clear intent")
        assert result.intent == IntentType.GENERAL


class TestEntityExtraction:
    """Test entity extraction."""

    def test_extract_relative_time_tomorrow(self, preprocessor):
        result = preprocessor.preprocess("Remind me tomorrow at 3pm")
        datetime_entity = result.get_entity("datetime")
        assert datetime_entity is not None

    def test_extract_relative_time_in_hours(self, preprocessor):
        result = preprocessor.preprocess("Call me in 2 hours")
        datetime_entity = result.get_entity("datetime")
        assert datetime_entity is not None
        # Should be approximately 2 hours from now
        expected = datetime.now() + timedelta(hours=2)
        assert abs((datetime_entity.value - expected).total_seconds()) < 60

    def test_extract_quoted_text(self, preprocessor):
        result = preprocessor.preprocess('Add task "buy milk"')
        quoted = result.get_entity("quoted_text")
        assert quoted is not None
        assert quoted.value == "buy milk"

    def test_extract_numbers(self, preprocessor):
        result = preprocessor.preprocess("Set priority to 5")
        number = result.get_entity("number")
        assert number is not None
        assert number.value == 5


class TestTextCleaning:
    """Test text cleaning."""

    def test_removes_extra_whitespace(self, preprocessor):
        result = preprocessor.preprocess("hello    world")
        assert result.cleaned_text == "hello world"

    def test_strips_whitespace(self, preprocessor):
        result = preprocessor.preprocess("  hello world  ")
        assert result.cleaned_text == "hello world"

    def test_preserves_original(self, preprocessor):
        original = "  Hello   World  "
        result = preprocessor.preprocess(original)
        assert result.original_text == original
