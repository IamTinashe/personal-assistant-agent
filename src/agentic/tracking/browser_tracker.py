"""Browser activity tracking for Chrome, Safari, Firefox."""

import asyncio
import json
import os
import platform
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

from agentic.tracking.base import (
    ActivityTracker,
    ActivityEvent,
    ActivityType,
    ApplicationCategory,
)


class BrowserTracker(ActivityTracker):
    """Tracks browser history and activity from Chrome, Safari, Firefox."""
    
    # Browser history database paths by OS
    BROWSER_PATHS = {
        "Darwin": {  # macOS
            "chrome": "~/Library/Application Support/Google/Chrome/Default/History",
            "chrome_canary": "~/Library/Application Support/Google/Chrome Canary/Default/History",
            "brave": "~/Library/Application Support/BraveSoftware/Brave-Browser/Default/History",
            "edge": "~/Library/Application Support/Microsoft Edge/Default/History",
            "firefox": "~/Library/Application Support/Firefox/Profiles/*/places.sqlite",
            "safari": "~/Library/Safari/History.db",
        },
        "Linux": {
            "chrome": "~/.config/google-chrome/Default/History",
            "brave": "~/.config/BraveSoftware/Brave-Browser/Default/History",
            "firefox": "~/.mozilla/firefox/*/places.sqlite",
            "edge": "~/.config/microsoft-edge/Default/History",
        },
        "Windows": {
            "chrome": "~/AppData/Local/Google/Chrome/User Data/Default/History",
            "brave": "~/AppData/Local/BraveSoftware/Brave-Browser/User Data/Default/History",
            "firefox": "~/AppData/Roaming/Mozilla/Firefox/Profiles/*/places.sqlite",
            "edge": "~/AppData/Local/Microsoft/Edge/User Data/Default/History",
        },
    }
    
    # Search engine patterns
    SEARCH_PATTERNS = {
        "google.com/search": "q",
        "bing.com/search": "q",
        "duckduckgo.com/": "q",
        "yahoo.com/search": "p",
        "search.brave.com/search": "q",
        "ecosia.org/search": "q",
    }
    
    def __init__(
        self,
        poll_interval: float = 30.0,
        lookback_minutes: int = 5,
        browsers: Optional[list[str]] = None,
    ):
        super().__init__("browser_tracker")
        self.poll_interval = poll_interval
        self.lookback_minutes = lookback_minutes
        self.browsers = browsers or ["chrome", "brave", "safari", "firefox", "edge"]
        self._task: Optional[asyncio.Task] = None
        self._last_urls: set[str] = set()
        self._system = platform.system()
    
    def _get_browser_path(self, browser: str) -> Optional[Path]:
        """Get the history database path for a browser."""
        paths = self.BROWSER_PATHS.get(self._system, {})
        path_pattern = paths.get(browser)
        
        if not path_pattern:
            return None
        
        expanded = os.path.expanduser(path_pattern)
        
        # Handle glob patterns (Firefox profiles)
        if "*" in expanded:
            import glob
            matches = glob.glob(expanded)
            if matches:
                return Path(matches[0])
            return None
        
        path = Path(expanded)
        return path if path.exists() else None
    
    def _copy_db_for_reading(self, db_path: Path) -> Optional[Path]:
        """Copy database to temp location (browsers lock the file)."""
        temp_path = Path(f"/tmp/browser_history_{db_path.name}")
        try:
            shutil.copy2(db_path, temp_path)
            return temp_path
        except (PermissionError, FileNotFoundError) as e:
            return None
    
    def _extract_search_query(self, url: str) -> Optional[str]:
        """Extract search query from URL if it's a search engine."""
        for pattern, param in self.SEARCH_PATTERNS.items():
            if pattern in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if param in params:
                    return params[param][0]
        return None
    
    def _get_chromium_history(
        self, db_path: Path, since: datetime
    ) -> list[ActivityEvent]:
        """Read history from Chromium-based browsers (Chrome, Brave, Edge)."""
        events = []
        temp_db = self._copy_db_for_reading(db_path)
        
        if not temp_db:
            return events
        
        try:
            conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Chrome stores timestamps as microseconds since 1601-01-01
            chrome_epoch = datetime(1601, 1, 1)
            since_chrome = int((since - chrome_epoch).total_seconds() * 1_000_000)
            
            cursor.execute("""
                SELECT url, title, visit_count, last_visit_time
                FROM urls
                WHERE last_visit_time > ?
                ORDER BY last_visit_time DESC
                LIMIT 100
            """, (since_chrome,))
            
            for url, title, visit_count, last_visit_time in cursor.fetchall():
                # Convert Chrome timestamp to datetime
                timestamp = chrome_epoch + timedelta(microseconds=last_visit_time)
                
                # Check if it's a search
                search_query = self._extract_search_query(url)
                
                event = ActivityEvent(
                    event_type=ActivityType.BROWSER_SEARCH if search_query else ActivityType.BROWSER_NAVIGATION,
                    application=db_path.parent.parent.name,
                    category=ApplicationCategory.BROWSER,
                    timestamp=timestamp,
                    title=title,
                    url=url,
                    content_snippet=search_query,
                    metadata={
                        "visit_count": visit_count,
                        "domain": urlparse(url).netloc,
                    },
                )
                events.append(event)
            
            conn.close()
        except Exception as e:
            pass
        finally:
            if temp_db and temp_db.exists():
                temp_db.unlink()
        
        return events
    
    def _get_firefox_history(
        self, db_path: Path, since: datetime
    ) -> list[ActivityEvent]:
        """Read history from Firefox."""
        events = []
        temp_db = self._copy_db_for_reading(db_path)
        
        if not temp_db:
            return events
        
        try:
            conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Firefox uses microseconds since Unix epoch
            since_ts = int(since.timestamp() * 1_000_000)
            
            cursor.execute("""
                SELECT p.url, p.title, p.visit_count, h.visit_date
                FROM moz_places p
                JOIN moz_historyvisits h ON p.id = h.place_id
                WHERE h.visit_date > ?
                ORDER BY h.visit_date DESC
                LIMIT 100
            """, (since_ts,))
            
            for url, title, visit_count, visit_date in cursor.fetchall():
                timestamp = datetime.fromtimestamp(visit_date / 1_000_000)
                search_query = self._extract_search_query(url)
                
                event = ActivityEvent(
                    event_type=ActivityType.BROWSER_SEARCH if search_query else ActivityType.BROWSER_NAVIGATION,
                    application="Firefox",
                    category=ApplicationCategory.BROWSER,
                    timestamp=timestamp,
                    title=title,
                    url=url,
                    content_snippet=search_query,
                    metadata={
                        "visit_count": visit_count,
                        "domain": urlparse(url).netloc,
                    },
                )
                events.append(event)
            
            conn.close()
        except Exception as e:
            pass
        finally:
            if temp_db and temp_db.exists():
                temp_db.unlink()
        
        return events
    
    def _get_safari_history(
        self, db_path: Path, since: datetime
    ) -> list[ActivityEvent]:
        """Read history from Safari (macOS only)."""
        events = []
        temp_db = self._copy_db_for_reading(db_path)
        
        if not temp_db:
            return events
        
        try:
            conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Safari uses seconds since 2001-01-01
            safari_epoch = datetime(2001, 1, 1)
            since_safari = (since - safari_epoch).total_seconds()
            
            cursor.execute("""
                SELECT hi.url, hv.title, hv.visit_time
                FROM history_items hi
                JOIN history_visits hv ON hi.id = hv.history_item
                WHERE hv.visit_time > ?
                ORDER BY hv.visit_time DESC
                LIMIT 100
            """, (since_safari,))
            
            for url, title, visit_time in cursor.fetchall():
                timestamp = safari_epoch + timedelta(seconds=visit_time)
                search_query = self._extract_search_query(url)
                
                event = ActivityEvent(
                    event_type=ActivityType.BROWSER_SEARCH if search_query else ActivityType.BROWSER_NAVIGATION,
                    application="Safari",
                    category=ApplicationCategory.BROWSER,
                    timestamp=timestamp,
                    title=title,
                    url=url,
                    content_snippet=search_query,
                    metadata={"domain": urlparse(url).netloc},
                )
                events.append(event)
            
            conn.close()
        except Exception as e:
            pass
        finally:
            if temp_db and temp_db.exists():
                temp_db.unlink()
        
        return events
    
    async def _poll_browsers(self) -> None:
        """Poll all browsers for new history."""
        while self._running:
            try:
                since = datetime.now() - timedelta(minutes=self.lookback_minutes)
                all_events = []
                
                for browser in self.browsers:
                    db_path = self._get_browser_path(browser)
                    if not db_path:
                        continue
                    
                    if browser in ["chrome", "brave", "edge", "chrome_canary"]:
                        events = self._get_chromium_history(db_path, since)
                    elif browser == "firefox":
                        events = self._get_firefox_history(db_path, since)
                    elif browser == "safari":
                        events = self._get_safari_history(db_path, since)
                    else:
                        continue
                    
                    all_events.extend(events)
                
                # Deduplicate and emit new events
                new_urls = set()
                for event in all_events:
                    if event.url and event.url not in self._last_urls:
                        new_urls.add(event.url)
                        await self._emit_event(event)
                
                self._last_urls = new_urls
                
            except Exception as e:
                pass
            
            await asyncio.sleep(self.poll_interval)
    
    async def start(self) -> None:
        """Start browser tracking."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._poll_browsers())
    
    async def stop(self) -> None:
        """Stop browser tracking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def get_current_activity(self) -> Optional[ActivityEvent]:
        """Get most recent browser activity."""
        since = datetime.now() - timedelta(minutes=1)
        
        for browser in self.browsers:
            db_path = self._get_browser_path(browser)
            if not db_path:
                continue
            
            if browser in ["chrome", "brave", "edge"]:
                events = self._get_chromium_history(db_path, since)
            elif browser == "firefox":
                events = self._get_firefox_history(db_path, since)
            elif browser == "safari":
                events = self._get_safari_history(db_path, since)
            else:
                continue
            
            if events:
                return events[0]
        
        return None
    
    async def get_recent_searches(self, minutes: int = 60) -> list[str]:
        """Get recent search queries."""
        since = datetime.now() - timedelta(minutes=minutes)
        searches = []
        
        for browser in self.browsers:
            db_path = self._get_browser_path(browser)
            if not db_path:
                continue
            
            if browser in ["chrome", "brave", "edge"]:
                events = self._get_chromium_history(db_path, since)
            elif browser == "firefox":
                events = self._get_firefox_history(db_path, since)
            elif browser == "safari":
                events = self._get_safari_history(db_path, since)
            else:
                continue
            
            for event in events:
                if event.event_type == ActivityType.BROWSER_SEARCH and event.content_snippet:
                    searches.append(event.content_snippet)
        
        return list(set(searches))
