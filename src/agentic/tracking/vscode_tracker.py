"""VS Code activity tracking via workspace state and extensions."""

import asyncio
import json
import os
import platform
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from agentic.tracking.base import (
    ActivityTracker,
    ActivityEvent,
    ActivityType,
    ApplicationCategory,
)


class VSCodeTracker(ActivityTracker):
    """Tracks VS Code activity including files opened, edited, and terminal commands."""
    
    # VS Code storage paths by OS
    VSCODE_PATHS = {
        "Darwin": {
            "state": "~/Library/Application Support/Code/User/globalStorage/state.vscdb",
            "history": "~/Library/Application Support/Code/User/History",
            "workspaces": "~/Library/Application Support/Code/User/workspaceStorage",
            "recent": "~/Library/Application Support/Code/storage.json",
        },
        "Linux": {
            "state": "~/.config/Code/User/globalStorage/state.vscdb",
            "history": "~/.config/Code/User/History",
            "workspaces": "~/.config/Code/User/workspaceStorage",
            "recent": "~/.config/Code/storage.json",
        },
        "Windows": {
            "state": "~/AppData/Roaming/Code/User/globalStorage/state.vscdb",
            "history": "~/AppData/Roaming/Code/User/History",
            "workspaces": "~/AppData/Roaming/Code/User/workspaceStorage",
            "recent": "~/AppData/Roaming/Code/storage.json",
        },
    }
    
    # Cursor IDE paths (similar to VS Code)
    CURSOR_PATHS = {
        "Darwin": {
            "state": "~/Library/Application Support/Cursor/User/globalStorage/state.vscdb",
            "history": "~/Library/Application Support/Cursor/User/History",
            "workspaces": "~/Library/Application Support/Cursor/User/workspaceStorage",
        },
        "Linux": {
            "state": "~/.config/Cursor/User/globalStorage/state.vscdb",
            "history": "~/.config/Cursor/User/History",
            "workspaces": "~/.config/Cursor/User/workspaceStorage",
        },
    }
    
    def __init__(
        self,
        poll_interval: float = 10.0,
        track_cursor: bool = True,
    ):
        super().__init__("vscode_tracker")
        self.poll_interval = poll_interval
        self.track_cursor = track_cursor
        self._task: Optional[asyncio.Task] = None
        self._system = platform.system()
        self._known_files: set[str] = set()
        self._last_workspace: Optional[str] = None
    
    def _get_path(self, key: str, is_cursor: bool = False) -> Optional[Path]:
        """Get VS Code/Cursor path for current OS."""
        paths = self.CURSOR_PATHS if is_cursor else self.VSCODE_PATHS
        os_paths = paths.get(self._system, {})
        path_str = os_paths.get(key)
        
        if not path_str:
            return None
        
        path = Path(os.path.expanduser(path_str))
        return path if path.exists() else None
    
    def _get_recent_workspaces(self) -> list[dict]:
        """Get recently opened workspaces from VS Code."""
        workspaces = []
        
        # Try VS Code storage.json
        recent_path = self._get_path("recent")
        if recent_path:
            try:
                with open(recent_path, "r") as f:
                    data = json.load(f)
                    # Extract recent folders/workspaces
                    entries = data.get("openedPathsList", {})
                    
                    for entry in entries.get("workspaces3", []):
                        if isinstance(entry, dict):
                            workspaces.append({
                                "path": entry.get("folderUri", ""),
                                "label": entry.get("label", ""),
                            })
                        elif isinstance(entry, str):
                            workspaces.append({"path": entry, "label": ""})
                    
                    for entry in entries.get("entries", []):
                        if isinstance(entry, dict):
                            workspaces.append({
                                "path": entry.get("folderUri", entry.get("fileUri", "")),
                                "label": entry.get("label", ""),
                            })
            except Exception:
                pass
        
        return workspaces[:10]  # Return top 10
    
    def _get_recent_files_from_history(self) -> list[dict]:
        """Get recently edited files from VS Code history folder."""
        files = []
        history_path = self._get_path("history")
        
        if not history_path:
            return files
        
        try:
            # Each subfolder in History contains entries.json with file info
            for entry_dir in history_path.iterdir():
                if not entry_dir.is_dir():
                    continue
                
                entries_file = entry_dir / "entries.json"
                if not entries_file.exists():
                    continue
                
                try:
                    with open(entries_file, "r") as f:
                        data = json.load(f)
                        
                        # Get the resource (file path)
                        resource = data.get("resource", "")
                        entries = data.get("entries", [])
                        
                        if resource and entries:
                            # Get the most recent entry timestamp
                            latest_entry = max(entries, key=lambda x: x.get("timestamp", 0))
                            
                            files.append({
                                "path": resource,
                                "timestamp": latest_entry.get("timestamp", 0),
                                "source": latest_entry.get("source", ""),
                            })
                except Exception:
                    continue
            
            # Sort by timestamp descending
            files.sort(key=lambda x: x["timestamp"], reverse=True)
            
        except Exception:
            pass
        
        return files[:50]  # Return top 50
    
    def _get_workspace_state(self) -> Optional[dict]:
        """Get current workspace state from state.vscdb."""
        state_path = self._get_path("state")
        
        if not state_path:
            return None
        
        try:
            conn = sqlite3.connect(f"file:{state_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Query the ItemTable for workspace info
            cursor.execute("""
                SELECT key, value FROM ItemTable
                WHERE key LIKE '%workbench%' OR key LIKE '%editor%' OR key LIKE '%terminal%'
                LIMIT 100
            """)
            
            state = {}
            for key, value in cursor.fetchall():
                try:
                    state[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    state[key] = value
            
            conn.close()
            return state
        except Exception:
            pass
        
        return None
    
    def _extract_file_path_from_uri(self, uri: str) -> str:
        """Extract clean file path from VS Code URI."""
        if uri.startswith("file://"):
            return uri[7:]
        return uri
    
    def _get_language_from_path(self, file_path: str) -> str:
        """Infer programming language from file extension."""
        ext_map = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".jsx": "React JSX",
            ".tsx": "React TSX",
            ".vue": "Vue",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".h": "C Header",
            ".cs": "C#",
            ".rb": "Ruby",
            ".php": "PHP",
            ".swift": "Swift",
            ".kt": "Kotlin",
            ".scala": "Scala",
            ".r": "R",
            ".sql": "SQL",
            ".html": "HTML",
            ".css": "CSS",
            ".scss": "SCSS",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".xml": "XML",
            ".md": "Markdown",
            ".sh": "Shell",
            ".bash": "Bash",
            ".zsh": "Zsh",
            ".dockerfile": "Dockerfile",
            ".tf": "Terraform",
        }
        
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "Unknown")
    
    async def _poll_vscode(self) -> None:
        """Poll VS Code for activity changes."""
        while self._running:
            try:
                now = datetime.now()
                
                # Check recent files
                recent_files = self._get_recent_files_from_history()
                
                for file_info in recent_files:
                    file_path = self._extract_file_path_from_uri(file_info["path"])
                    file_key = f"{file_path}_{file_info['timestamp']}"
                    
                    if file_key not in self._known_files:
                        self._known_files.add(file_key)
                        
                        # Convert timestamp (ms since epoch)
                        timestamp = datetime.fromtimestamp(file_info["timestamp"] / 1000)
                        
                        # Only emit events from the last hour
                        if now - timestamp < timedelta(hours=1):
                            event = ActivityEvent(
                                event_type=ActivityType.FILE_EDIT,
                                application="Visual Studio Code",
                                category=ApplicationCategory.CODE_EDITOR,
                                timestamp=timestamp,
                                title=Path(file_path).name,
                                file_path=file_path,
                                metadata={
                                    "language": self._get_language_from_path(file_path),
                                    "source": file_info.get("source", ""),
                                    "directory": str(Path(file_path).parent),
                                },
                            )
                            await self._emit_event(event)
                
                # Limit the known files set size
                if len(self._known_files) > 1000:
                    # Keep only the most recent 500
                    self._known_files = set(list(self._known_files)[-500:])
                
            except Exception as e:
                pass
            
            await asyncio.sleep(self.poll_interval)
    
    async def start(self) -> None:
        """Start VS Code tracking."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._poll_vscode())
    
    async def stop(self) -> None:
        """Stop VS Code tracking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def get_current_activity(self) -> Optional[ActivityEvent]:
        """Get most recent VS Code activity."""
        recent_files = self._get_recent_files_from_history()
        
        if not recent_files:
            return None
        
        file_info = recent_files[0]
        file_path = self._extract_file_path_from_uri(file_info["path"])
        timestamp = datetime.fromtimestamp(file_info["timestamp"] / 1000)
        
        return ActivityEvent(
            event_type=ActivityType.FILE_EDIT,
            application="Visual Studio Code",
            category=ApplicationCategory.CODE_EDITOR,
            timestamp=timestamp,
            title=Path(file_path).name,
            file_path=file_path,
            metadata={
                "language": self._get_language_from_path(file_path),
            },
        )
    
    async def get_current_project(self) -> Optional[str]:
        """Get the current project/workspace being worked on."""
        workspaces = self._get_recent_workspaces()
        
        if workspaces:
            path = workspaces[0].get("path", "")
            return self._extract_file_path_from_uri(path)
        
        return None
    
    async def get_files_worked_on_today(self) -> list[str]:
        """Get list of files worked on today."""
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_ts = today_start.timestamp() * 1000
        
        recent_files = self._get_recent_files_from_history()
        
        files = []
        for file_info in recent_files:
            if file_info["timestamp"] >= today_start_ts:
                file_path = self._extract_file_path_from_uri(file_info["path"])
                if file_path not in files:
                    files.append(file_path)
        
        return files
