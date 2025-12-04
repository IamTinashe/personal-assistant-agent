"""Client to communicate with the external activity tracker daemon."""

import asyncio
from datetime import datetime
from typing import Any, Optional

import httpx

from agentic.core.logging import LoggerMixin


class ActivityTrackerClient(LoggerMixin):
    """
    Client to communicate with the activity tracker daemon.
    
    Used when the assistant runs in Docker but the tracker
    runs on the host machine.
    """
    
    def __init__(
        self,
        host: str = "host.docker.internal",  # Docker's host reference
        port: int = 8001,
        timeout: float = 5.0,
    ):
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._available: Optional[bool] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def is_available(self) -> bool:
        """Check if the tracker daemon is running."""
        if self._available is not None:
            return self._available
        
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/health")
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        
        return self._available
    
    async def get_context(self) -> dict[str, Any]:
        """Get current activity context from the tracker."""
        if not await self.is_available():
            return {"tracking": False, "error": "Tracker not available"}
        
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/context")
            return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to get activity context: {e}")
            return {"tracking": False, "error": str(e)}
    
    async def get_summary(self, hours: int = 1) -> dict[str, Any]:
        """Get activity summary from the tracker."""
        if not await self.is_available():
            return {"text": "Activity tracker not available"}
        
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/summary",
                params={"hours": hours},
            )
            return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to get activity summary: {e}")
            return {"text": f"Error: {e}"}
    
    async def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent events from the tracker."""
        if not await self.is_available():
            return []
        
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/events",
                params={"limit": limit},
            )
            return response.json()
        except Exception as e:
            self.logger.warning(f"Failed to get events: {e}")
            return []
    
    def get_context_for_prompt(self, context: dict[str, Any]) -> str:
        """Format context for inclusion in AI prompt."""
        if not context.get("tracking", True):
            return ""
        
        lines = ["Recent user activity:"]
        
        if context.get("current_activity"):
            act = context["current_activity"]
            lines.append(f"- Currently in: {act.get('application', 'unknown')}")
            if act.get("title"):
                lines.append(f"  Title: {act['title']}")
        
        if context.get("recent_files"):
            files = context["recent_files"][:5]
            from pathlib import Path
            file_names = [Path(f).name for f in files]
            lines.append(f"- Recent files: {', '.join(file_names)}")
        
        if context.get("recent_searches"):
            searches = context["recent_searches"][:3]
            lines.append(f"- Recent searches: {', '.join(searches)}")
        
        if context.get("current_project"):
            lines.append(f"- Project: {context['current_project']}")
        
        return "\n".join(lines)
    
    async def answer_activity_question(self, question: str) -> Optional[str]:
        """Answer questions about user's activity by querying the daemon."""
        if not await self.is_available():
            return None
        
        try:
            # Use the daemon's /ask endpoint for intelligent answers
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/ask",
                json={"question": question},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("answer")
        except Exception as e:
            self.logger.warning(f"Failed to ask activity question: {e}")
        
        # Fallback to local processing
        context = await self.get_context()
        
        if not context.get("tracking", True):
            return None
        
        question_lower = question.lower()
        
        # What am I working on?
        if any(w in question_lower for w in ["working on", "doing", "current", "building"]):
            parts = []
            if context.get("current_activity"):
                act = context["current_activity"]
                parts.append(f"You're in {act.get('application', 'unknown')}")
                if act.get("title"):
                    parts.append(f"({act['title']})")
            
            if context.get("project_info"):
                proj = context["project_info"]
                if proj.get("project_name"):
                    parts.append(f"Project: {proj['project_name']}")
                if proj.get("frameworks"):
                    parts.append(f"Stack: {', '.join(proj['frameworks'])}")
            
            if context.get("recent_files"):
                from pathlib import Path
                files = [Path(f).name for f in context["recent_files"][:3]]
                parts.append(f"Recent files: {', '.join(files)}")
            
            return " | ".join(parts) if parts else None
        
        # What did I search?
        if any(w in question_lower for w in ["search", "looked up", "googled"]):
            if context.get("recent_searches"):
                return f"Recent searches: {', '.join(context['recent_searches'][:10])}"
            return "No recent searches tracked."
        
        # What files?
        if any(w in question_lower for w in ["file", "code", "edit"]):
            if context.get("recent_files"):
                from pathlib import Path
                files = [Path(f).name for f in context["recent_files"][:10]]
                return f"Files worked on: {', '.join(files)}"
            return "No file activity tracked."
        
        # Summary
        if any(w in question_lower for w in ["summary", "overview", "today"]):
            summary = await self.get_summary(hours=8)
            return summary.get("text", "No summary available.")
        
        return None
    
    async def get_work_context(self) -> str:
        """Get rich work context for LLM prompt."""
        if not await self.is_available():
            return ""
        
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/work-context")
            if response.status_code == 200:
                data = response.json()
                return data.get("context", "")
        except Exception as e:
            self.logger.warning(f"Failed to get work context: {e}")
        
        return ""
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
