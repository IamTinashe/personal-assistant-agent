"""Activity aggregator that combines all trackers and provides context to the assistant."""

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from agentic.tracking.base import (
    ActivityEvent,
    ActivitySummary,
    ActivityType,
    ApplicationCategory,
)
from agentic.tracking.browser_tracker import BrowserTracker
from agentic.tracking.window_tracker import WindowTracker
from agentic.tracking.vscode_tracker import VSCodeTracker
from agentic.tracking.context_builder import ContextBuilder, ProjectDetector
from agentic.tracking.screen_reader import ScreenReader, get_screen_reader
from agentic.tracking.vision_analyzer import VisionAnalyzer, get_vision_analyzer


class ActivityAggregator:
    """Aggregates activity from all trackers and provides context for the assistant."""
    
    def __init__(
        self,
        data_dir: str = "./data/activity",
        enable_browser: bool = True,
        enable_window: bool = True,
        enable_vscode: bool = True,
        enable_screen_reader: bool = True,
        enable_vision: bool = True,
        max_events_in_memory: int = 1000,
        memory_store_callback: Optional[Callable] = None,
        memory_search_callback: Optional[Callable] = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._events: list[ActivityEvent] = []
        self._max_events = max_events_in_memory
        self._running = False
        self.enable_screen_reader = enable_screen_reader
        self.enable_vision = enable_vision
        self._screen_reader: Optional[ScreenReader] = None
        self._vision_analyzer: Optional[VisionAnalyzer] = None
        
        # Initialize context builder
        self.context_builder = ContextBuilder(
            memory_store_callback=memory_store_callback,
            memory_search_callback=memory_search_callback,
        )
        
        # Background context update task
        self._context_task: Optional[asyncio.Task] = None
        
        # Initialize trackers
        self.trackers = []
        
        if enable_browser:
            self.browser_tracker = BrowserTracker()
            self.browser_tracker.register_callback(self._on_event)
            self.trackers.append(self.browser_tracker)
        else:
            self.browser_tracker = None
        
        if enable_window:
            self.window_tracker = WindowTracker()
            self.window_tracker.register_callback(self._on_event)
            self.trackers.append(self.window_tracker)
        else:
            self.window_tracker = None
        
        if enable_vscode:
            self.vscode_tracker = VSCodeTracker()
            self.vscode_tracker.register_callback(self._on_event)
            self.trackers.append(self.vscode_tracker)
        else:
            self.vscode_tracker = None
        
        # Load persisted events
        self._load_events()
    
    async def _on_event(self, event: ActivityEvent) -> None:
        """Handle new activity event."""
        self._events.append(event)
        
        # Trim events if over limit
        if len(self._events) > self._max_events:
            self._events = self._events[-self._max_events:]
        
        # Persist periodically (every 50 events)
        if len(self._events) % 50 == 0:
            self._save_events()
    
    def _save_events(self) -> None:
        """Persist events to disk."""
        today = datetime.now().strftime("%Y-%m-%d")
        events_file = self.data_dir / f"events_{today}.json"
        
        today_events = [
            e.to_dict() for e in self._events
            if e.timestamp.date() == datetime.now().date()
        ]
        
        try:
            with open(events_file, "w") as f:
                json.dump(today_events, f, indent=2)
        except Exception:
            pass
    
    def _load_events(self) -> None:
        """Load persisted events from disk."""
        today = datetime.now().strftime("%Y-%m-%d")
        events_file = self.data_dir / f"events_{today}.json"
        
        if events_file.exists():
            try:
                with open(events_file, "r") as f:
                    data = json.load(f)
                    self._events = [ActivityEvent.from_dict(e) for e in data]
            except Exception:
                pass
    
    async def start(self) -> None:
        """Start all activity trackers."""
        if self._running:
            return
        
        self._running = True
        
        for tracker in self.trackers:
            await tracker.start()
        
        # Start background context updater
        self._context_task = asyncio.create_task(self._update_context_periodically())
    
    async def _update_context_periodically(self) -> None:
        """Periodically update work context."""
        while self._running:
            try:
                await self._refresh_context()
            except Exception:
                pass
            await asyncio.sleep(30)  # Update every 30 seconds
    
    async def _refresh_context(self) -> None:
        """Refresh the current work context."""
        # Get recent files
        recent_files = []
        if self.vscode_tracker:
            recent_files = await self.vscode_tracker.get_files_worked_on_today()
        
        # Get current app
        current_app = None
        if self.window_tracker:
            activity = await self.window_tracker.get_current_activity()
            if activity:
                current_app = activity.application
        
        # Get recent searches
        recent_searches = []
        if self.browser_tracker:
            recent_searches = await self.browser_tracker.get_recent_searches(minutes=60)
        
        # Update context builder
        await self.context_builder.update_context(
            recent_files=recent_files,
            current_app=current_app,
            recent_searches=recent_searches,
        )
        
        # Periodically store in memory
        await self.context_builder.store_context_in_memory()
    
    async def stop(self) -> None:
        """Stop all activity trackers."""
        self._running = False
        
        # Stop context updater
        if self._context_task:
            self._context_task.cancel()
            try:
                await self._context_task
            except asyncio.CancelledError:
                pass
        
        for tracker in self.trackers:
            await tracker.stop()
        
        self._save_events()
    
    def get_events(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        event_types: Optional[list[ActivityType]] = None,
        categories: Optional[list[ApplicationCategory]] = None,
        limit: int = 100,
    ) -> list[ActivityEvent]:
        """Get filtered activity events."""
        events = self._events
        
        if since:
            events = [e for e in events if e.timestamp >= since]
        
        if until:
            events = [e for e in events if e.timestamp <= until]
        
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        if categories:
            events = [e for e in events if e.category in categories]
        
        # Sort by timestamp descending
        events.sort(key=lambda e: e.timestamp, reverse=True)
        
        return events[:limit]
    
    def get_summary(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> ActivitySummary:
        """Get activity summary for a time period."""
        if not since:
            since = datetime.now() - timedelta(hours=1)
        if not until:
            until = datetime.now()
        
        events = self.get_events(since=since, until=until, limit=10000)
        
        # Calculate durations by app
        app_durations: dict[str, float] = defaultdict(float)
        category_durations: dict[str, float] = defaultdict(float)
        
        for event in events:
            if event.duration_seconds:
                app_durations[event.application] += event.duration_seconds
                category_durations[event.category.value] += event.duration_seconds
        
        # Calculate active/idle time
        active_duration = sum(
            e.duration_seconds or 0 for e in events
            if e.event_type != ActivityType.IDLE
        )
        idle_duration = sum(
            e.duration_seconds or 0 for e in events
            if e.event_type == ActivityType.IDLE
        )
        
        # Get unique files and URLs
        files = list(set(e.file_path for e in events if e.file_path))
        urls = list(set(e.url for e in events if e.url))
        searches = list(set(
            e.content_snippet for e in events
            if e.event_type == ActivityType.BROWSER_SEARCH and e.content_snippet
        ))
        
        # Sort durations
        top_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)[:5]
        top_categories = sorted(category_durations.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return ActivitySummary(
            start_time=since,
            end_time=until,
            total_events=len(events),
            active_duration_seconds=active_duration,
            idle_duration_seconds=idle_duration,
            top_applications=top_apps,
            top_categories=top_categories,
            files_worked_on=files,
            urls_visited=urls,
            searches_performed=searches,
        )
    
    async def get_current_context(self) -> dict[str, Any]:
        """Get current activity context for the AI assistant."""
        # Refresh context first
        await self._refresh_context()
        
        context = {
            "timestamp": datetime.now().isoformat(),
            "current_activity": None,
            "recent_files": [],
            "recent_searches": [],
            "recent_urls": [],
            "current_project": None,
            "project_info": self.context_builder.current_context.get("project", {}),
            "summary": None,
        }
        
        # Get current window
        if self.window_tracker:
            current = await self.window_tracker.get_current_activity()
            if current:
                context["current_activity"] = {
                    "application": current.application,
                    "category": current.category.value,
                    "title": current.title,
                }
        
        # Get VS Code context
        if self.vscode_tracker:
            current_project = await self.vscode_tracker.get_current_project()
            if current_project:
                context["current_project"] = current_project
            
            files_today = await self.vscode_tracker.get_files_worked_on_today()
            context["recent_files"] = files_today[:10]
        
        # Get browser context
        if self.browser_tracker:
            searches = await self.browser_tracker.get_recent_searches(minutes=60)
            context["recent_searches"] = searches[:5]
        
        # Get recent URLs from events
        recent_events = self.get_events(
            since=datetime.now() - timedelta(minutes=30),
            event_types=[ActivityType.BROWSER_NAVIGATION],
            limit=10,
        )
        context["recent_urls"] = [
            {"title": e.title, "url": e.url, "domain": e.metadata.get("domain")}
            for e in recent_events if e.url
        ]
        
        # Get rich summary from context builder
        context["summary"] = self.context_builder._generate_summary()
        context["work_context"] = await self.context_builder.get_work_context_for_llm()
        
        return context
    
    def get_context_for_prompt(self, max_tokens: int = 500) -> str:
        """Get activity context formatted for inclusion in AI prompt."""
        events = self.get_events(
            since=datetime.now() - timedelta(minutes=30),
            limit=20,
        )
        
        if not events:
            return "No recent activity tracked."
        
        lines = ["Recent user activity:"]
        
        # Group by category
        by_category: dict[str, list[ActivityEvent]] = defaultdict(list)
        for event in events:
            by_category[event.category.value].append(event)
        
        for category, cat_events in by_category.items():
            if category == "code_editor":
                files = list(set(e.file_path for e in cat_events if e.file_path))[:5]
                if files:
                    lines.append(f"- Coding: {', '.join(Path(f).name for f in files)}")
            
            elif category == "browser":
                searches = [e.content_snippet for e in cat_events if e.event_type == ActivityType.BROWSER_SEARCH]
                urls = [e.metadata.get("domain") for e in cat_events if e.url]
                
                if searches:
                    lines.append(f"- Searched: {', '.join(searches[:3])}")
                if urls:
                    unique_domains = list(set(urls))[:5]
                    lines.append(f"- Browsing: {', '.join(d for d in unique_domains if d)}")
            
            elif category == "document":
                docs = list(set(e.title for e in cat_events if e.title))[:3]
                if docs:
                    lines.append(f"- Documents: {', '.join(docs)}")
            
            elif category == "communication":
                apps = list(set(e.application for e in cat_events))[:3]
                if apps:
                    lines.append(f"- Communication: {', '.join(apps)}")
        
        return "\n".join(lines)
    
    async def answer_activity_question(self, question: str) -> str:
        """Answer questions about user's activity."""
        # Refresh context first
        await self._refresh_context()
        
        question_lower = question.lower()
        
        # Vision-based understanding - check FIRST for explicit vision requests
        # Keywords like "understand", "analyze", "see", "happening" suggest visual analysis
        vision_keywords = ["understand", "analyze screen", "explain what", "what's happening", 
                          "describe screen", "tell me about the screen", "what do you see",
                          "help me understand", "can you see", "analyze this", "what is this",
                          "what's going on", "going on on my screen", "summarize my screen",
                          "summarize the screen", "summarize screen"]
        if any(w in question_lower for w in vision_keywords):
            if self.enable_vision:
                if not self._vision_analyzer:
                    self._vision_analyzer = get_vision_analyzer()
                try:
                    # Use GPT-4 Vision to understand the screen
                    analysis = await self._vision_analyzer.answer_about_screen(question)
                    return analysis
                except Exception as e:
                    return f"Error analyzing screen with vision: {e}"
            # Fall through to context-based answer if vision not enabled
        
        # Help with errors on screen
        if any(w in question_lower for w in ["error", "issue", "bug", "fix this", "what's wrong", "debug"]):
            if self.enable_vision:
                if not self._vision_analyzer:
                    self._vision_analyzer = get_vision_analyzer()
                try:
                    return await self._vision_analyzer.explain_error()
                except Exception as e:
                    return f"Error analyzing screen for errors: {e}"
        
        # Explain code on screen
        if any(w in question_lower for w in ["explain code", "explain this code", "what does this code", "code do"]):
            if self.enable_vision:
                if not self._vision_analyzer:
                    self._vision_analyzer = get_vision_analyzer()
                try:
                    return await self._vision_analyzer.explain_code()
                except Exception as e:
                    return f"Error analyzing code: {e}"
        
        # Summarize what's on screen - use vision for rich summary
        if any(w in question_lower for w in ["summarize screen", "summarize what's on", "give me a summary of the screen"]):
            if self.enable_vision:
                if not self._vision_analyzer:
                    self._vision_analyzer = get_vision_analyzer()
                try:
                    summary = await self._vision_analyzer.summarize_screen()
                    return summary
                except Exception as e:
                    return f"Error summarizing screen: {e}"
            # Fall back to OCR
            if self.enable_screen_reader:
                if not self._screen_reader:
                    self._screen_reader = get_screen_reader()
                try:
                    screen_text = await self._screen_reader.get_screen_summary(max_chars=2000)
                    return f"**Screen Content (OCR):**\n{screen_text}"
                except Exception:
                    pass
            return "Screen analysis not available."
        
        # Read what's on screen / what am I seeing / what's on my screen (use OCR for text extraction)
        if any(w in question_lower for w in ["see on", "seeing", "on my screen", "read screen", "what's on screen", 
                                               "screen shows", "looking at", "displayed", "showing"]):
            if self.enable_screen_reader:
                if not self._screen_reader:
                    self._screen_reader = get_screen_reader()
                try:
                    screen_text = await self._screen_reader.get_screen_summary(max_chars=3000)
                    if screen_text and screen_text != "Could not read screen content.":
                        # Get window context too
                        window_info = ""
                        if self.window_tracker:
                            activity = await self.window_tracker.get_current_activity()
                            if activity:
                                window_info = f"**{activity.application}**"
                                if activity.title:
                                    window_info += f" - {activity.title}"
                        
                        response = f"📺 Currently viewing: {window_info}\n\n"
                        response += f"**Screen Content:**\n```\n{screen_text}\n```"
                        return response
                except Exception as e:
                    return f"Error reading screen: {e}"
            return "Screen reading not enabled."
        
        # Which window/app am I on?
        if any(w in question_lower for w in ["window", "app", "application", "screen", "where am i", "browser"]):
            if self.window_tracker:
                activity = await self.window_tracker.get_current_activity()
                if activity:
                    response = f"You're currently in **{activity.application}**"
                    if activity.title:
                        response += f"\n📄 Tab/Window: {activity.title}"
                    if activity.url:
                        response += f"\n🔗 URL: {activity.url}"
                    response += f"\n(Category: {activity.category.value})"
                    return response
            return "Couldn't detect current window."
        
        # What am I working on?
        if any(w in question_lower for w in ["working on", "doing", "current", "building"]):
            context = await self.get_current_context()
            
            parts = []
            if context["current_activity"]:
                act = context["current_activity"]
                parts.append(f"You're currently in {act['application']}")
                if act["title"]:
                    parts.append(f"({act['title']})")
            
            project_info = context.get("project_info", {})
            if project_info.get("project_name"):
                parts.append(f"Working on: {project_info['project_name']}")
                if project_info.get("frameworks"):
                    parts.append(f"Stack: {', '.join(project_info['frameworks'])}")
            
            if context["recent_files"]:
                files = [Path(f).name for f in context["recent_files"][:3]]
                parts.append(f"Recent files: {', '.join(files)}")
            
            return " | ".join(parts) if parts else "No activity tracked yet."
        
        # What did I search for?
        if any(w in question_lower for w in ["search", "looked up", "googled"]):
            if self.browser_tracker:
                searches = await self.browser_tracker.get_recent_searches(minutes=120)
                if searches:
                    return f"Recent searches: {', '.join(searches[:10])}"
            return "No recent searches found."
        
        # What files did I work on?
        if any(w in question_lower for w in ["file", "code", "edit"]):
            if self.vscode_tracker:
                files = await self.vscode_tracker.get_files_worked_on_today()
                if files:
                    file_names = [Path(f).name for f in files[:10]]
                    return f"Files worked on today: {', '.join(file_names)}"
            return "No file activity tracked."
        
        # Summary
        if any(w in question_lower for w in ["summary", "overview", "today"]):
            summary = self.get_summary(
                since=datetime.now().replace(hour=0, minute=0, second=0),
            )
            return summary.to_natural_language()
        
        # Default: return work context
        return await self.context_builder.get_work_context_for_llm() or self.get_context_for_prompt()
