"""Base classes for activity tracking."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import hashlib
import json


class ActivityType(str, Enum):
    """Types of tracked activities."""
    
    WINDOW_FOCUS = "window_focus"
    BROWSER_NAVIGATION = "browser_navigation"
    BROWSER_SEARCH = "browser_search"
    FILE_OPEN = "file_open"
    FILE_EDIT = "file_edit"
    FILE_SAVE = "file_save"
    CODE_CHANGE = "code_change"
    TERMINAL_COMMAND = "terminal_command"
    APPLICATION_LAUNCH = "application_launch"
    APPLICATION_CLOSE = "application_close"
    DOCUMENT_OPEN = "document_open"
    DOCUMENT_EDIT = "document_edit"
    MEETING_START = "meeting_start"
    MEETING_END = "meeting_end"
    IDLE = "idle"
    ACTIVE = "active"


class ApplicationCategory(str, Enum):
    """Categories of applications."""
    
    BROWSER = "browser"
    CODE_EDITOR = "code_editor"
    TERMINAL = "terminal"
    DOCUMENT = "document"
    COMMUNICATION = "communication"
    MEDIA = "media"
    PRODUCTIVITY = "productivity"
    SYSTEM = "system"
    OTHER = "other"


@dataclass
class ActivityEvent:
    """Represents a single activity event."""
    
    event_type: ActivityType
    application: str
    category: ApplicationCategory
    timestamp: datetime = field(default_factory=datetime.now)
    title: Optional[str] = None
    url: Optional[str] = None
    file_path: Optional[str] = None
    content_snippet: Optional[str] = None
    duration_seconds: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    
    @property
    def event_id(self) -> str:
        """Generate unique ID for the event."""
        content = f"{self.timestamp.isoformat()}{self.event_type}{self.application}{self.title}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "application": self.application,
            "category": self.category.value,
            "timestamp": self.timestamp.isoformat(),
            "title": self.title,
            "url": self.url,
            "file_path": self.file_path,
            "content_snippet": self.content_snippet,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }
    
    def to_embedding_text(self) -> str:
        """Convert to text for embedding/memory storage."""
        parts = [
            f"Activity: {self.event_type.value}",
            f"App: {self.application} ({self.category.value})",
            f"Time: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.content_snippet:
            parts.append(f"Content: {self.content_snippet[:200]}")
        if self.duration_seconds:
            parts.append(f"Duration: {self.duration_seconds:.1f}s")
            
        return " | ".join(parts)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivityEvent":
        """Create from dictionary."""
        return cls(
            event_type=ActivityType(data["event_type"]),
            application=data["application"],
            category=ApplicationCategory(data["category"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            title=data.get("title"),
            url=data.get("url"),
            file_path=data.get("file_path"),
            content_snippet=data.get("content_snippet"),
            duration_seconds=data.get("duration_seconds"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ActivitySummary:
    """Summary of activities over a time period."""
    
    start_time: datetime
    end_time: datetime
    total_events: int
    active_duration_seconds: float
    idle_duration_seconds: float
    top_applications: list[tuple[str, float]]  # (app, duration)
    top_categories: list[tuple[str, float]]  # (category, duration)
    files_worked_on: list[str]
    urls_visited: list[str]
    searches_performed: list[str]
    
    def to_natural_language(self) -> str:
        """Convert summary to natural language for the AI."""
        lines = [
            f"Activity summary from {self.start_time.strftime('%H:%M')} to {self.end_time.strftime('%H:%M')}:",
            f"- Total active time: {self.active_duration_seconds / 60:.1f} minutes",
            f"- Idle time: {self.idle_duration_seconds / 60:.1f} minutes",
        ]
        
        if self.top_applications:
            apps = ", ".join([f"{app} ({dur/60:.1f}m)" for app, dur in self.top_applications[:3]])
            lines.append(f"- Top apps: {apps}")
        
        if self.files_worked_on:
            files = ", ".join(self.files_worked_on[:5])
            lines.append(f"- Files: {files}")
        
        if self.urls_visited:
            urls = ", ".join(self.urls_visited[:5])
            lines.append(f"- Websites: {urls}")
        
        if self.searches_performed:
            searches = ", ".join(self.searches_performed[:3])
            lines.append(f"- Searches: {searches}")
        
        return "\n".join(lines)


class ActivityTracker(ABC):
    """Abstract base class for activity trackers."""
    
    def __init__(self, name: str):
        self.name = name
        self._running = False
        self._callbacks: list[callable] = []
    
    @abstractmethod
    async def start(self) -> None:
        """Start tracking activities."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop tracking activities."""
        pass
    
    @abstractmethod
    async def get_current_activity(self) -> Optional[ActivityEvent]:
        """Get the current activity."""
        pass
    
    def register_callback(self, callback: callable) -> None:
        """Register a callback for new events."""
        self._callbacks.append(callback)
    
    async def _emit_event(self, event: ActivityEvent) -> None:
        """Emit an event to all registered callbacks."""
        for callback in self._callbacks:
            try:
                await callback(event)
            except Exception as e:
                print(f"Error in callback: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if tracker is running."""
        return self._running
