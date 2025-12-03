"""
Centralized logging configuration with rich formatting.

Provides structured logging with file and console handlers.
"""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.logging import RichHandler

if TYPE_CHECKING:
    from agentic.core.config import Settings


def setup_logging(settings: "Settings") -> logging.Logger:
    """
    Configure application logging with rich console and file handlers.
    
    Args:
        settings: Application settings containing log configuration.
        
    Returns:
        logging.Logger: Configured root logger for the application.
    """
    # Ensure log directory exists
    settings.log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Create console handler with rich formatting
    console = Console(stderr=True)
    rich_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=True,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
    )
    rich_handler.setLevel(settings.log_level)
    
    # Create file handler
    file_handler = logging.FileHandler(
        settings.log_file,
        mode="a",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Log everything to file
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    
    # Configure root logger
    root_logger = logging.getLogger("agentic")
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(rich_handler)
    root_logger.addHandler(file_handler)
    
    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a child logger with the given name.
    
    Args:
        name: Logger name (typically module name).
        
    Returns:
        logging.Logger: Child logger instance.
    """
    return logging.getLogger(f"agentic.{name}")


class LoggerMixin:
    """
    Mixin class that provides a logger property.
    
    Usage:
        class MyClass(LoggerMixin):
            def my_method(self):
                self.logger.info("Doing something")
    """

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return get_logger(self.__class__.__name__)
