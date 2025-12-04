"""
Context builder that continuously tracks activity and builds rich context for the AI.

This module periodically analyzes user activity and stores insights in memory
so the AI can answer questions like "what am I building?" intelligently.
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from agentic.tracking.base import ActivityEvent, ActivityType, ApplicationCategory


class ProjectDetector:
    """Detects project information from file paths and activity."""
    
    # Project markers - files that indicate project root
    PROJECT_MARKERS = [
        "package.json",
        "pyproject.toml", 
        "setup.py",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "Makefile",
        "docker-compose.yml",
        "README.md",
        ".git",
    ]
    
    # Framework detection patterns
    FRAMEWORK_PATTERNS = {
        "nuxt": ["nuxt.config", ".nuxt", "pages/", "composables/"],
        "next.js": ["next.config", "pages/", "app/", "_app."],
        "vue": [".vue", "vue.config", "vite.config"],
        "react": ["react", "jsx", "tsx", "create-react-app"],
        "django": ["manage.py", "wsgi.py", "settings.py", "urls.py"],
        "fastapi": ["fastapi", "uvicorn"],
        "flask": ["flask", "app.py"],
        "express": ["express", "node_modules"],
        "terraform": [".tf", "terraform"],
        "docker": ["Dockerfile", "docker-compose"],
        "kubernetes": [".yaml", "kubectl", "k8s"],
    }
    
    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": "Python",
        ".js": "JavaScript", 
        ".ts": "TypeScript",
        ".jsx": "React",
        ".tsx": "React TypeScript",
        ".vue": "Vue.js",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
        ".php": "PHP",
        ".swift": "Swift",
        ".kt": "Kotlin",
        ".tf": "Terraform",
        ".sql": "SQL",
        ".sh": "Shell",
    }
    
    def detect_project_root(self, file_path: str) -> Optional[str]:
        """Find the project root from a file path."""
        path = Path(file_path)
        
        # Walk up the directory tree
        for parent in [path] + list(path.parents):
            if not parent.exists():
                continue
            for marker in self.PROJECT_MARKERS:
                if (parent / marker).exists():
                    return str(parent)
        
        return None
    
    def detect_project_info(self, file_paths: list[str]) -> dict[str, Any]:
        """Analyze file paths to detect project information."""
        if not file_paths:
            return {}
        
        # Find common project root
        roots = []
        for fp in file_paths:
            root = self.detect_project_root(fp)
            if root:
                roots.append(root)
        
        # Get most common root
        project_root = None
        if roots:
            from collections import Counter
            project_root = Counter(roots).most_common(1)[0][0]
        
        # Detect languages
        languages = set()
        for fp in file_paths:
            ext = Path(fp).suffix.lower()
            if ext in self.LANGUAGE_MAP:
                languages.add(self.LANGUAGE_MAP[ext])
        
        # Detect frameworks
        frameworks = set()
        all_paths_str = " ".join(file_paths).lower()
        for framework, patterns in self.FRAMEWORK_PATTERNS.items():
            if any(p in all_paths_str for p in patterns):
                frameworks.add(framework)
        
        # Try to get project name from root
        project_name = None
        if project_root:
            project_name = Path(project_root).name
            
            # Try to read package.json or pyproject.toml for name
            pkg_json = Path(project_root) / "package.json"
            pyproject = Path(project_root) / "pyproject.toml"
            
            if pkg_json.exists():
                try:
                    with open(pkg_json) as f:
                        data = json.load(f)
                        project_name = data.get("name", project_name)
                except:
                    pass
            elif pyproject.exists():
                try:
                    with open(pyproject) as f:
                        content = f.read()
                        match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                        if match:
                            project_name = match.group(1)
                except:
                    pass
        
        return {
            "project_name": project_name,
            "project_root": project_root,
            "languages": list(languages),
            "frameworks": list(frameworks),
            "file_count": len(file_paths),
        }


class ContextBuilder:
    """
    Builds and maintains rich context about user's work.
    
    Periodically analyzes activity and stores insights in memory.
    """
    
    def __init__(
        self,
        memory_store_callback: Optional[Callable] = None,
        memory_search_callback: Optional[Callable] = None,
        update_interval: float = 60.0,  # seconds
    ):
        self.memory_store = memory_store_callback
        self.memory_search = memory_search_callback
        self.update_interval = update_interval
        self.project_detector = ProjectDetector()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._current_context: dict[str, Any] = {}
        self._last_stored: Optional[datetime] = None
    
    @property
    def current_context(self) -> dict[str, Any]:
        """Get current work context."""
        return self._current_context
    
    async def update_context(
        self,
        recent_files: list[str],
        current_app: Optional[str] = None,
        recent_searches: Optional[list[str]] = None,
        recent_urls: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Update context based on recent activity."""
        
        # Detect project info from files
        project_info = self.project_detector.detect_project_info(recent_files)
        
        # Build context
        self._current_context = {
            "timestamp": datetime.now().isoformat(),
            "current_app": current_app,
            "project": project_info,
            "recent_files": recent_files[:10],
            "recent_searches": recent_searches or [],
            "recent_urls": recent_urls or [],
        }
        
        # Generate natural language summary
        self._current_context["summary"] = self._generate_summary()
        
        return self._current_context
    
    def _generate_summary(self) -> str:
        """Generate a natural language summary of current work."""
        ctx = self._current_context
        parts = []
        
        project = ctx.get("project", {})
        
        if project.get("project_name"):
            parts.append(f"Working on project: {project['project_name']}")
        
        if project.get("frameworks"):
            parts.append(f"Using: {', '.join(project['frameworks'])}")
        
        if project.get("languages"):
            parts.append(f"Languages: {', '.join(project['languages'])}")
        
        if ctx.get("recent_files"):
            file_names = [Path(f).name for f in ctx["recent_files"][:5]]
            parts.append(f"Recent files: {', '.join(file_names)}")
        
        if ctx.get("recent_searches"):
            parts.append(f"Researching: {', '.join(ctx['recent_searches'][:3])}")
        
        return " | ".join(parts) if parts else "No recent activity"
    
    async def store_context_in_memory(self) -> None:
        """Store current context as a memory entry."""
        if not self.memory_store:
            return
        
        ctx = self._current_context
        if not ctx:
            return
        
        # Don't store too frequently
        if self._last_stored:
            if datetime.now() - self._last_stored < timedelta(minutes=5):
                return
        
        # Create memory entry
        project = ctx.get("project", {})
        
        if project.get("project_name"):
            memory_text = f"User is working on {project['project_name']}"
            
            if project.get("frameworks"):
                memory_text += f" using {', '.join(project['frameworks'])}"
            
            if project.get("languages"):
                memory_text += f" with {', '.join(project['languages'])}"
            
            if ctx.get("recent_files"):
                file_names = [Path(f).name for f in ctx["recent_files"][:3]]
                memory_text += f". Currently editing: {', '.join(file_names)}"
            
            memory_text += f" (as of {datetime.now().strftime('%Y-%m-%d %H:%M')})"
            
            try:
                await self.memory_store(memory_text)
                self._last_stored = datetime.now()
            except Exception:
                pass
    
    async def get_work_context_for_llm(self) -> str:
        """Get formatted context for LLM prompt."""
        ctx = self._current_context
        
        if not ctx:
            return ""
        
        lines = ["[Current Work Context]"]
        
        project = ctx.get("project", {})
        
        if project.get("project_name"):
            lines.append(f"Project: {project['project_name']}")
        
        if project.get("project_root"):
            lines.append(f"Location: {project['project_root']}")
        
        if project.get("frameworks"):
            lines.append(f"Stack: {', '.join(project['frameworks'])}")
        
        if project.get("languages"):
            lines.append(f"Languages: {', '.join(project['languages'])}")
        
        if ctx.get("current_app"):
            lines.append(f"Current App: {ctx['current_app']}")
        
        if ctx.get("recent_files"):
            file_names = [Path(f).name for f in ctx["recent_files"][:5]]
            lines.append(f"Editing: {', '.join(file_names)}")
        
        if ctx.get("recent_searches"):
            lines.append(f"Researching: {', '.join(ctx['recent_searches'][:3])}")
        
        return "\n".join(lines)
    
    async def answer_context_question(self, question: str) -> Optional[str]:
        """Answer questions about current work context."""
        question_lower = question.lower()
        ctx = self._current_context
        project = ctx.get("project", {})
        
        # What am I building/working on?
        if any(w in question_lower for w in ["building", "working on", "project"]):
            if project.get("project_name"):
                answer = f"You're working on **{project['project_name']}**"
                
                if project.get("frameworks"):
                    answer += f", a {', '.join(project['frameworks'])} project"
                
                if project.get("languages"):
                    answer += f" using {', '.join(project['languages'])}"
                
                if ctx.get("recent_files"):
                    file_names = [Path(f).name for f in ctx["recent_files"][:3]]
                    answer += f". You've been editing: {', '.join(file_names)}"
                
                return answer
            else:
                return None  # Let LLM handle it
        
        # What stack/technology?
        if any(w in question_lower for w in ["stack", "technology", "framework", "using"]):
            if project.get("frameworks") or project.get("languages"):
                parts = []
                if project.get("frameworks"):
                    parts.append(f"Frameworks: {', '.join(project['frameworks'])}")
                if project.get("languages"):
                    parts.append(f"Languages: {', '.join(project['languages'])}")
                return " | ".join(parts)
        
        # What files?
        if any(w in question_lower for w in ["file", "editing", "code"]):
            if ctx.get("recent_files"):
                file_names = [Path(f).name for f in ctx["recent_files"][:10]]
                return f"Recent files: {', '.join(file_names)}"
        
        return None
