"""
Base skill interface for the task orchestrator.

Defines the contract that all skills must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agentic.preprocessing.preprocessor import IntentType, PreprocessedInput


class SkillPriority(int, Enum):
    """Skill execution priority levels."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class SkillResult:
    """
    Result of a skill execution.
    
    Attributes:
        success: Whether the skill executed successfully.
        message: Human-readable result message.
        data: Structured data from the skill execution.
        should_respond: Whether the assistant should generate a response.
        response_hint: Optional hint for response generation.
    """

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    should_respond: bool = True
    response_hint: str | None = None


class BaseSkill(ABC):
    """
    Abstract base class for all skills.
    
    Skills are modular handlers for specific types of tasks.
    They receive preprocessed input and return structured results.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this skill does."""
        pass

    @property
    @abstractmethod
    def supported_intents(self) -> list[IntentType]:
        """List of intents this skill can handle."""
        pass

    @property
    def priority(self) -> SkillPriority:
        """Execution priority for this skill."""
        return SkillPriority.NORMAL

    @property
    def requires_confirmation(self) -> bool:
        """Whether this skill requires user confirmation before executing."""
        return False

    @abstractmethod
    async def can_handle(self, preprocessed: PreprocessedInput) -> bool:
        """
        Check if this skill can handle the given input.
        
        Args:
            preprocessed: The preprocessed user input.
            
        Returns:
            bool: True if this skill can handle the input.
        """
        pass

    @abstractmethod
    async def execute(self, preprocessed: PreprocessedInput) -> SkillResult:
        """
        Execute the skill with the given input.
        
        Args:
            preprocessed: The preprocessed user input.
            
        Returns:
            SkillResult: The result of the skill execution.
        """
        pass

    async def setup(self) -> None:
        """
        Optional setup method called when the skill is registered.
        
        Override this to initialize resources like database connections.
        """
        pass

    async def teardown(self) -> None:
        """
        Optional teardown method called when the assistant shuts down.
        
        Override this to clean up resources.
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name})>"
