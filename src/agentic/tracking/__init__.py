"""Activity tracking module for monitoring user behavior across applications."""

from agentic.tracking.base import ActivityTracker, ActivityEvent
from agentic.tracking.window_tracker import WindowTracker
from agentic.tracking.browser_tracker import BrowserTracker
from agentic.tracking.vscode_tracker import VSCodeTracker
from agentic.tracking.aggregator import ActivityAggregator
from agentic.tracking.client import ActivityTrackerClient

__all__ = [
    "ActivityTracker",
    "ActivityEvent", 
    "WindowTracker",
    "BrowserTracker",
    "VSCodeTracker",
    "ActivityAggregator",
    "ActivityTrackerClient",
]
