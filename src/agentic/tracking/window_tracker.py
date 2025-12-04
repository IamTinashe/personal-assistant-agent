"""Active window and application tracking."""

import asyncio
import platform
import subprocess
from datetime import datetime
from typing import Optional

from agentic.tracking.base import (
    ActivityTracker,
    ActivityEvent,
    ActivityType,
    ApplicationCategory,
)


class WindowTracker(ActivityTracker):
    """Tracks the active window and application focus."""
    
    # Application to category mapping
    APP_CATEGORIES = {
        # Browsers
        "google chrome": ApplicationCategory.BROWSER,
        "chrome": ApplicationCategory.BROWSER,
        "safari": ApplicationCategory.BROWSER,
        "firefox": ApplicationCategory.BROWSER,
        "brave browser": ApplicationCategory.BROWSER,
        "microsoft edge": ApplicationCategory.BROWSER,
        "arc": ApplicationCategory.BROWSER,
        
        # Code editors (Electron is VS Code on macOS)
        "electron": ApplicationCategory.CODE_EDITOR,
        "code": ApplicationCategory.CODE_EDITOR,
        "code - insiders": ApplicationCategory.CODE_EDITOR,
        "visual studio code": ApplicationCategory.CODE_EDITOR,
        "vscode": ApplicationCategory.CODE_EDITOR,
        "sublime text": ApplicationCategory.CODE_EDITOR,
        "atom": ApplicationCategory.CODE_EDITOR,
        "intellij idea": ApplicationCategory.CODE_EDITOR,
        "pycharm": ApplicationCategory.CODE_EDITOR,
        "webstorm": ApplicationCategory.CODE_EDITOR,
        "vim": ApplicationCategory.CODE_EDITOR,
        "neovim": ApplicationCategory.CODE_EDITOR,
        "cursor": ApplicationCategory.CODE_EDITOR,
        "xcode": ApplicationCategory.CODE_EDITOR,
        "zed": ApplicationCategory.CODE_EDITOR,
        
        # Terminals
        "terminal": ApplicationCategory.TERMINAL,
        "iterm": ApplicationCategory.TERMINAL,
        "iterm2": ApplicationCategory.TERMINAL,
        "hyper": ApplicationCategory.TERMINAL,
        "alacritty": ApplicationCategory.TERMINAL,
        "kitty": ApplicationCategory.TERMINAL,
        "warp": ApplicationCategory.TERMINAL,
        
        # Documents
        "microsoft word": ApplicationCategory.DOCUMENT,
        "pages": ApplicationCategory.DOCUMENT,
        "google docs": ApplicationCategory.DOCUMENT,
        "notion": ApplicationCategory.DOCUMENT,
        "obsidian": ApplicationCategory.DOCUMENT,
        "bear": ApplicationCategory.DOCUMENT,
        "evernote": ApplicationCategory.DOCUMENT,
        "microsoft excel": ApplicationCategory.DOCUMENT,
        "numbers": ApplicationCategory.DOCUMENT,
        "microsoft powerpoint": ApplicationCategory.DOCUMENT,
        "keynote": ApplicationCategory.DOCUMENT,
        "preview": ApplicationCategory.DOCUMENT,
        "adobe acrobat": ApplicationCategory.DOCUMENT,
        
        # Communication
        "slack": ApplicationCategory.COMMUNICATION,
        "discord": ApplicationCategory.COMMUNICATION,
        "microsoft teams": ApplicationCategory.COMMUNICATION,
        "zoom": ApplicationCategory.COMMUNICATION,
        "messages": ApplicationCategory.COMMUNICATION,
        "mail": ApplicationCategory.COMMUNICATION,
        "microsoft outlook": ApplicationCategory.COMMUNICATION,
        "telegram": ApplicationCategory.COMMUNICATION,
        "whatsapp": ApplicationCategory.COMMUNICATION,
        
        # Media
        "spotify": ApplicationCategory.MEDIA,
        "apple music": ApplicationCategory.MEDIA,
        "vlc": ApplicationCategory.MEDIA,
        "quicktime player": ApplicationCategory.MEDIA,
        "youtube": ApplicationCategory.MEDIA,
        
        # Productivity
        "finder": ApplicationCategory.PRODUCTIVITY,
        "calendar": ApplicationCategory.PRODUCTIVITY,
        "reminders": ApplicationCategory.PRODUCTIVITY,
        "notes": ApplicationCategory.PRODUCTIVITY,
        "todoist": ApplicationCategory.PRODUCTIVITY,
        "things": ApplicationCategory.PRODUCTIVITY,
        "linear": ApplicationCategory.PRODUCTIVITY,
        "jira": ApplicationCategory.PRODUCTIVITY,
        "figma": ApplicationCategory.PRODUCTIVITY,
        "sketch": ApplicationCategory.PRODUCTIVITY,
        
        # System
        "system preferences": ApplicationCategory.SYSTEM,
        "system settings": ApplicationCategory.SYSTEM,
        "activity monitor": ApplicationCategory.SYSTEM,
    }
    
    def __init__(
        self,
        poll_interval: float = 2.0,
        idle_threshold_seconds: float = 300.0,
    ):
        super().__init__("window_tracker")
        self.poll_interval = poll_interval
        self.idle_threshold = idle_threshold_seconds
        self._task: Optional[asyncio.Task] = None
        self._last_window: Optional[str] = None
        self._last_app: Optional[str] = None
        self._window_start: Optional[datetime] = None
        self._system = platform.system()
    
    def _get_category(self, app_name: str) -> ApplicationCategory:
        """Get category for an application."""
        app_lower = app_name.lower()
        
        for key, category in self.APP_CATEGORIES.items():
            if key in app_lower:
                return category
        
        return ApplicationCategory.OTHER
    
    def _get_idle_time_macos(self) -> float:
        """Get system idle time on macOS (seconds)."""
        try:
            result = subprocess.run(
                ["ioreg", "-c", "IOHIDSystem"],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.split("\n"):
                if "HIDIdleTime" in line:
                    # Value is in nanoseconds
                    idle_ns = int(line.split("=")[-1].strip())
                    return idle_ns / 1_000_000_000
        except Exception:
            pass
        return 0.0
    
    def _get_active_window_macos(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get active window info on macOS using AppleScript.
        
        Returns:
            Tuple of (app_name, window_title, url)
        """
        # First get the app name
        app_script = '''
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
        end tell
        return frontApp
        '''
        
        try:
            result = subprocess.run(
                ["osascript", "-e", app_script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            
            if result.returncode != 0:
                return None, None, None
            
            app_name = result.stdout.strip()
            
            if not app_name:
                return None, None, None
            
            # Now try to get the window title and URL
            window_title = None
            url = None
            
            # Try different methods based on the app
            if app_name == "Google Chrome":
                # Get both title and URL from Chrome
                chrome_script = '''
                tell application "Google Chrome"
                    set tabTitle to title of active tab of front window
                    set tabURL to URL of active tab of front window
                    return tabTitle & "|||" & tabURL
                end tell
                '''
                try:
                    chrome_result = subprocess.run(
                        ["osascript", "-e", chrome_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if chrome_result.returncode == 0:
                        output = chrome_result.stdout.strip()
                        if "|||" in output:
                            parts = output.split("|||")
                            window_title = parts[0]
                            url = parts[1] if len(parts) > 1 else None
                except Exception:
                    pass
                    
            elif app_name == "Brave Browser":
                brave_script = '''
                tell application "Brave Browser"
                    set tabTitle to title of active tab of front window
                    set tabURL to URL of active tab of front window
                    return tabTitle & "|||" & tabURL
                end tell
                '''
                try:
                    brave_result = subprocess.run(
                        ["osascript", "-e", brave_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if brave_result.returncode == 0:
                        output = brave_result.stdout.strip()
                        if "|||" in output:
                            parts = output.split("|||")
                            window_title = parts[0]
                            url = parts[1] if len(parts) > 1 else None
                except Exception:
                    pass
                    
            elif app_name == "Safari":
                safari_script = '''
                tell application "Safari"
                    set docName to name of front document
                    set docURL to URL of front document
                    return docName & "|||" & docURL
                end tell
                '''
                try:
                    safari_result = subprocess.run(
                        ["osascript", "-e", safari_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if safari_result.returncode == 0:
                        output = safari_result.stdout.strip()
                        if "|||" in output:
                            parts = output.split("|||")
                            window_title = parts[0]
                            url = parts[1] if len(parts) > 1 else None
                except Exception:
                    pass
                    
            elif app_name == "Arc":
                arc_script = '''
                tell application "Arc"
                    set tabTitle to title of active tab of front window
                    set tabURL to URL of active tab of front window
                    return tabTitle & "|||" & tabURL
                end tell
                '''
                try:
                    arc_result = subprocess.run(
                        ["osascript", "-e", arc_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if arc_result.returncode == 0:
                        output = arc_result.stdout.strip()
                        if "|||" in output:
                            parts = output.split("|||")
                            window_title = parts[0]
                            url = parts[1] if len(parts) > 1 else None
                except Exception:
                    pass
            else:
                # Generic window title for other apps
                title_script = f'''
                tell application "System Events"
                    tell process "{app_name}"
                        set windowTitle to name of front window
                    end tell
                end tell
                return windowTitle
                '''
                try:
                    title_result = subprocess.run(
                        ["osascript", "-e", title_script],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if title_result.returncode == 0:
                        window_title = title_result.stdout.strip()
                except Exception:
                    pass
            
            return app_name, window_title, url
            
        except Exception:
            pass
        
        return None, None, None
    
    def _get_active_window_linux(self) -> tuple[Optional[str], Optional[str]]:
        """Get active window info on Linux using xdotool."""
        try:
            # Get active window ID
            window_id = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
            ).stdout.strip()
            
            if not window_id:
                return None, None
            
            # Get window name
            window_name = subprocess.run(
                ["xdotool", "getwindowname", window_id],
                capture_output=True,
                text=True,
            ).stdout.strip()
            
            # Get window PID and process name
            pid = subprocess.run(
                ["xdotool", "getwindowpid", window_id],
                capture_output=True,
                text=True,
            ).stdout.strip()
            
            if pid:
                app_name = subprocess.run(
                    ["ps", "-p", pid, "-o", "comm="],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            else:
                app_name = "Unknown"
            
            return app_name, window_name
        except Exception:
            pass
        
        return None, None
    
    def _get_active_window(self) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Get active window info based on OS.
        
        Returns:
            Tuple of (app_name, window_title, url)
        """
        if self._system == "Darwin":
            return self._get_active_window_macos()
        elif self._system == "Linux":
            app, title = self._get_active_window_linux()
            return app, title, None
        else:
            # Windows - would need pywin32
            return None, None, None
    
    def _get_idle_time(self) -> float:
        """Get system idle time based on OS."""
        if self._system == "Darwin":
            return self._get_idle_time_macos()
        # Linux/Windows would need additional implementation
        return 0.0
    
    async def _poll_windows(self) -> None:
        """Poll for active window changes."""
        while self._running:
            try:
                app_name, window_title, url = self._get_active_window()
                idle_time = self._get_idle_time()
                now = datetime.now()
                
                # Check for idle
                if idle_time > self.idle_threshold:
                    if self._last_app:
                        # Emit idle event
                        event = ActivityEvent(
                            event_type=ActivityType.IDLE,
                            application="System",
                            category=ApplicationCategory.SYSTEM,
                            timestamp=now,
                            duration_seconds=idle_time,
                        )
                        await self._emit_event(event)
                        self._last_app = None
                        self._last_window = None
                    
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                # Check for window/app change
                if app_name and (app_name != self._last_app or window_title != self._last_window):
                    # Calculate duration on previous window
                    duration = None
                    if self._window_start:
                        duration = (now - self._window_start).total_seconds()
                    
                    # Emit window focus event
                    category = self._get_category(app_name)
                    event = ActivityEvent(
                        event_type=ActivityType.WINDOW_FOCUS,
                        application=app_name,
                        category=category,
                        timestamp=now,
                        title=window_title,
                        url=url,
                        duration_seconds=duration,
                        metadata={
                            "previous_app": self._last_app,
                            "previous_window": self._last_window,
                        },
                    )
                    await self._emit_event(event)
                    
                    # Update state
                    self._last_app = app_name
                    self._last_window = window_title
                    self._window_start = now
                
            except Exception as e:
                pass
            
            await asyncio.sleep(self.poll_interval)
    
    async def start(self) -> None:
        """Start window tracking."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._poll_windows())
    
    async def stop(self) -> None:
        """Stop window tracking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def get_current_activity(self) -> Optional[ActivityEvent]:
        """Get current active window."""
        app_name, window_title, url = self._get_active_window()
        
        if not app_name:
            return None
        
        return ActivityEvent(
            event_type=ActivityType.WINDOW_FOCUS,
            application=app_name,
            category=self._get_category(app_name),
            timestamp=datetime.now(),
            title=window_title,
            url=url,
        )
