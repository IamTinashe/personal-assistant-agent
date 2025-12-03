"""
Custom exceptions for the Agentic application.

Provides a hierarchy of exceptions for better error handling.
"""

from typing import Any


class AgenticError(Exception):
    """Base exception for all Agentic errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ConfigurationError(AgenticError):
    """Raised when there's a configuration problem."""

    pass


class OpenAIError(AgenticError):
    """Raised when OpenAI API calls fail."""

    pass


class EmbeddingError(AgenticError):
    """Raised when embedding generation fails."""

    pass


class VectorStoreError(AgenticError):
    """Raised when vector store operations fail."""

    pass


class MemoryError(AgenticError):
    """Raised when memory operations fail."""

    pass


class PreprocessingError(AgenticError):
    """Raised when input preprocessing fails."""

    pass


class TaskExecutionError(AgenticError):
    """Raised when task execution fails."""

    pass


class SkillError(AgenticError):
    """Raised when a skill encounters an error."""

    pass


class VoiceError(AgenticError):
    """Raised when voice processing fails."""

    pass


class DatabaseError(AgenticError):
    """Raised when database operations fail."""

    pass


class IntegrationError(AgenticError):
    """Raised when external integration fails."""

    pass


class AuthenticationError(AgenticError):
    """Raised when authentication fails."""

    pass


class RateLimitError(OpenAIError):
    """Raised when API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ContextTooLongError(OpenAIError):
    """Raised when the context exceeds model limits."""

    def __init__(
        self,
        message: str = "Context too long",
        tokens_used: int | None = None,
        max_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.tokens_used = tokens_used
        self.max_tokens = max_tokens
