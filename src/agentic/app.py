"""
Main assistant application that coordinates all components.

This is the primary entry point for the Agentic assistant.
"""

from typing import Any, AsyncGenerator

from agentic.core.config import Settings, get_settings
from agentic.core.logging import LoggerMixin, setup_logging
from agentic.llm.openai_client import OpenAIClient
from agentic.llm.response import ResponseGenerator
from agentic.memory.manager import MemoryManager
from agentic.orchestrator.orchestrator import TaskOrchestrator
from agentic.preprocessing.context import ContextManager
from agentic.preprocessing.preprocessor import InputPreprocessor, IntentType
from agentic.skills.notes import NotesSkill
from agentic.skills.reminder import ReminderSkill
from agentic.skills.tasks import TaskSkill
from agentic.tracking.aggregator import ActivityAggregator
from agentic.tracking.client import ActivityTrackerClient


class Assistant(LoggerMixin):
    """
    Main personal assistant application.
    
    Coordinates all components:
    - Input preprocessing
    - Task orchestration
    - Memory management
    - LLM response generation
    - Voice I/O (optional)
    
    Usage:
        assistant = Assistant()
        await assistant.initialize()
        
        response = await assistant.chat("Set a reminder for tomorrow at 3pm")
        print(response)
        
        await assistant.shutdown()
    
    Args:
        settings: Optional settings override.
        enable_voice: Whether to enable voice I/O.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        enable_voice: bool = False,
        enable_activity_tracking: bool = True,
    ) -> None:
        self.settings = settings or get_settings()
        self.enable_voice = enable_voice
        self.enable_activity_tracking = enable_activity_tracking
        
        # Core components
        self._preprocessor: InputPreprocessor | None = None
        self._orchestrator: TaskOrchestrator | None = None
        self._openai: OpenAIClient | None = None
        self._memory: MemoryManager | None = None
        self._context: ContextManager | None = None
        self._response_generator: ResponseGenerator | None = None
        
        # Activity tracking
        self._activity: ActivityAggregator | None = None
        self._activity_client: ActivityTrackerClient | None = None
        
        # Voice components (optional)
        self._stt = None
        self._tts = None
        self._recorder = None
        
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize all assistant components."""
        if self._initialized:
            return
        
        # Setup logging
        self.settings.ensure_directories()
        setup_logging(self.settings)
        self.logger.info("Initializing assistant...")
        
        # Initialize OpenAI client
        self._openai = OpenAIClient(self.settings)
        await self._openai.initialize()
        
        # Initialize memory with embedding generator
        self._memory = MemoryManager(
            settings=self.settings,
            embedding_generator=self._openai.generate_embedding,
        )
        await self._memory.initialize()
        
        # Initialize preprocessor
        self._preprocessor = InputPreprocessor()
        
        # Initialize context manager
        self._context = ContextManager(
            settings=self.settings,
            memory_manager=self._memory,
        )
        
        # Initialize response generator
        self._response_generator = ResponseGenerator(
            settings=self.settings,
            openai_client=self._openai,
            memory_manager=self._memory,
            context_manager=self._context,
        )
        
        # Initialize orchestrator and register skills
        self._orchestrator = TaskOrchestrator()
        self._orchestrator.register_skill(ReminderSkill())
        self._orchestrator.register_skill(NotesSkill())
        self._orchestrator.register_skill(TaskSkill())
        await self._orchestrator.initialize()
        
        # Initialize voice components if enabled
        if self.enable_voice:
            await self._init_voice()
        
        # Initialize activity tracking if enabled
        if self.enable_activity_tracking:
            await self._init_activity_tracking()
        
        self._initialized = True
        self.logger.info("Assistant initialized successfully")

    async def _init_voice(self) -> None:
        """Initialize voice I/O components."""
        from agentic.voice import AudioRecorder, SpeechToText, TextToSpeech
        
        self._stt = SpeechToText(self.settings)
        self._tts = TextToSpeech(self.settings)
        self._recorder = AudioRecorder()
        
        await self._stt.initialize()
        await self._tts.initialize()
        
        self.logger.info("Voice I/O initialized")

    async def _init_activity_tracking(self) -> None:
        """Initialize activity tracking components."""
        import os
        
        # Check if running in Docker
        in_docker = os.path.exists("/.dockerenv") or os.environ.get("DOCKER_CONTAINER")
        
        if in_docker:
            # Use client to connect to external tracker daemon
            self._activity_client = ActivityTrackerClient(
                host="host.docker.internal",
                port=8001,
            )
            if await self._activity_client.is_available():
                self.logger.info("Connected to external activity tracker")
            else:
                self.logger.warning(
                    "Activity tracker not available. "
                    "Run './run_tracker.sh' on host machine."
                )
        else:
            # Run tracker directly (local development)
            data_dir = self.settings.vector_store_path.parent / "activity"
            self._activity = ActivityAggregator(
                data_dir=str(data_dir),
                enable_browser=True,
                enable_window=True,
                enable_vscode=True,
            )
            await self._activity.start()
            self.logger.info("Activity tracking initialized")

    async def chat(
        self,
        message: str,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """
        Process a chat message and generate a response.
        
        Args:
            message: User's message.
            stream: Whether to stream the response.
            
        Returns:
            str | AsyncGenerator: The response or a stream of chunks.
        """
        self._ensure_initialized()
        
        # Preprocess input
        preprocessed = self._preprocessor.preprocess(message)
        
        self.logger.info(
            f"Processing: '{message[:50]}...' "
            f"(intent: {preprocessed.intent.value})"
        )
        
        # Check if this is an activity-related question
        if self._is_activity_question(message):
            activity_response = await self._get_activity_answer(message)
            if activity_response:
                # If streaming requested, wrap in async generator
                if stream:
                    async def _stream_activity():
                        yield activity_response
                    return _stream_activity()
                return activity_response
        
        # Try task orchestrator first
        handled, skill_result = await self._orchestrator.process(preprocessed)
        
        # Get activity context for LLM
        activity_context = await self._get_activity_context_for_prompt()
        
        # Generate response
        if handled and skill_result and not skill_result.should_respond:
            # Skill provided complete response
            response = skill_result.message
        else:
            # Generate LLM response with activity context
            response = await self._response_generator.generate_response(
                preprocessed=preprocessed,
                skill_result=skill_result if handled else None,
                stream=stream,
                additional_context=activity_context,
            )
        
        if not stream:
            self.logger.debug(f"Response: {response[:100]}...")
        
        return response

    def _is_activity_question(self, message: str) -> bool:
        """Check if the message is asking about user's activity."""
        activity_keywords = [
            "what am i working",
            "what am i doing",
            "what am i building",
            "what did i search",
            "what files",
            "what have i been",
            "my activity",
            "what sites",
            "what websites",
            "recent activity",
            "today's summary",
            "what project",
            "check what i",
            "show my activity",
            "current project",
            "what code",
            "which files",
            "which window",
            "what window",
            "current window",
            "what app",
            "which app",
            "current app",
            "what application",
            "what browser",
            "where am i",
            "what screen",
            # Screen reading keywords
            "what do you see",
            "what can you see",
            "what's on my screen",
            "what is on my screen",
            "read my screen",
            "read the screen",
            "what am i looking at",
            "what am i seeing",
            "what's displayed",
            "what is displayed",
            "what's showing",
            "screen shows",
            "see on screen",
            "what text",
            "read this",
            "what does it say",
            "summarize screen",
            "describe screen",
            # Vision/AI understanding keywords
            "understand this",
            "understand what",
            "analyze screen",
            "analyze this",
            "explain what you see",
            "explain what's on",
            "what's happening",
            "what is happening",
            "what's going on",
            "going on on my screen",
            "summarize my screen",
            "summarize the screen",
            "help me understand",
            "can you see this",
            "can you see my",
            "what do you see on",
            "tell me about the screen",
            "what is this",
            # Error/debugging keywords
            "fix this error",
            "what's wrong",
            "debug this",
            "explain this error",
            "help with error",
            # Code explanation keywords
            "explain this code",
            "what does this code",
            "explain code",
        ]
        message_lower = message.lower()
        return any(kw in message_lower for kw in activity_keywords)

    async def _get_activity_answer(self, message: str) -> str | None:
        """Get answer to activity-related question."""
        if self._activity:
            return await self._activity.answer_activity_question(message)
        elif self._activity_client:
            return await self._activity_client.answer_activity_question(message)
        return None

    async def _get_activity_context_for_prompt(self) -> str | None:
        """Get activity context for LLM prompt."""
        if self._activity:
            return self._activity.get_context_for_prompt()
        elif self._activity_client:
            context = await self._activity_client.get_context()
            return self._activity_client.get_context_for_prompt(context)
        return None

    async def chat_voice(self) -> str:
        """
        Record voice input and generate a voice response.
        
        Returns:
            str: The text response (also spoken via TTS).
        """
        self._ensure_initialized()
        
        if not self._recorder or not self._stt or not self._tts:
            raise RuntimeError("Voice I/O not initialized")
        
        # Record audio
        audio_data = await self._recorder.record_until_silence()
        
        # Transcribe
        transcript = await self._stt.transcribe_bytes(audio_data)
        self.logger.info(f"Heard: {transcript}")
        
        # Process
        response = await self.chat(transcript)
        
        # Speak response
        await self._tts.speak(response)
        
        return response

    async def remember(self, fact: str) -> str:
        """
        Store a fact in long-term memory.
        
        Args:
            fact: The fact to remember.
            
        Returns:
            str: Confirmation message.
        """
        self._ensure_initialized()
        
        await self._memory.store_fact(fact)
        return f"I'll remember: {fact}"

    async def recall(self, query: str, k: int = 5) -> list[str]:
        """
        Search memory for relevant information.
        
        Args:
            query: Search query.
            k: Number of results to return.
            
        Returns:
            list[str]: Relevant memories.
        """
        self._ensure_initialized()
        
        results = await self._memory.search_memories(query, k=k)
        return [r.entry.content for r in results]

    async def new_session(self) -> None:
        """Start a new conversation session (clears conversation buffer)."""
        self._ensure_initialized()
        
        await self._memory.clear_conversation_buffer()
        self._context.clear_session_context()
        self.logger.info("Started new session")

    def get_capabilities(self) -> str:
        """Get a description of the assistant's capabilities."""
        return self._orchestrator.get_capabilities() if self._orchestrator else ""

    async def get_stats(self) -> dict[str, Any]:
        """Get assistant statistics."""
        self._ensure_initialized()
        
        stats = {
            "memory": await self._memory.get_stats(),
            "skills": self._orchestrator.list_skills(),
        }
        
        if self._activity:
            context = await self._activity.get_current_context()
            stats["activity"] = {
                "current": context.get("current_activity"),
                "files_today": len(context.get("recent_files", [])),
                "tracking": True,
            }
        
        return stats

    async def get_activity_context(self) -> dict[str, Any]:
        """Get current activity context."""
        self._ensure_initialized()
        
        if self._activity:
            return await self._activity.get_current_context()
        elif self._activity_client:
            return await self._activity_client.get_context()
        return {"tracking": False}

    async def get_activity_summary(self, hours: int = 1) -> str:
        """Get activity summary for the past N hours."""
        self._ensure_initialized()
        
        if self._activity:
            from datetime import datetime, timedelta
            summary = self._activity.get_summary(
                since=datetime.now() - timedelta(hours=hours),
            )
            return summary.to_natural_language()
        elif self._activity_client:
            result = await self._activity_client.get_summary(hours=hours)
            return result.get("text", "Activity tracker not available.")
        return "Activity tracking not enabled."

    async def shutdown(self) -> None:
        """Shutdown the assistant and release resources."""
        if not self._initialized:
            return
        
        self.logger.info("Shutting down assistant...")
        
        # Stop activity tracking
        if self._activity:
            await self._activity.stop()
        if self._activity_client:
            await self._activity_client.close()
        
        # Save memory
        if self._memory:
            await self._memory.close()
        
        # Shutdown orchestrator
        if self._orchestrator:
            await self._orchestrator.shutdown()
        
        # Close OpenAI client
        if self._openai:
            await self._openai.close()
        
        # Close voice components
        if self._stt:
            await self._stt.close()
        if self._tts:
            await self._tts.close()
        
        self._initialized = False
        self.logger.info("Assistant shutdown complete")

    def _ensure_initialized(self) -> None:
        """Ensure the assistant is initialized."""
        if not self._initialized:
            raise RuntimeError(
                "Assistant not initialized. Call initialize() first."
            )

    async def __aenter__(self) -> "Assistant":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.shutdown()
