"""
Core module containing shared configuration, logging, and utilities.
"""

from agentic.core.config import Settings, get_settings
from agentic.core.exceptions import (
    AgenticError,
    ConfigurationError,
    EmbeddingError,
    MemoryError,
    OpenAIError,
    PreprocessingError,
    SkillError,
    TaskExecutionError,
    VectorStoreError,
    VoiceError,
)
from agentic.core.logging import LoggerMixin, get_logger, setup_logging

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Logging
    "setup_logging",
    "get_logger",
    "LoggerMixin",
    # Exceptions
    "AgenticError",
    "ConfigurationError",
    "OpenAIError",
    "EmbeddingError",
    "VectorStoreError",
    "MemoryError",
    "PreprocessingError",
    "TaskExecutionError",
    "SkillError",
    "VoiceError",
]
