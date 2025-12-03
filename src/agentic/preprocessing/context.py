"""
Context manager for building and managing conversation context.

Handles context window management and prompt construction.
"""

from dataclasses import dataclass, field
from typing import Any

from agentic.core.config import Settings
from agentic.core.logging import LoggerMixin
from agentic.memory.manager import MemoryManager
from agentic.preprocessing.preprocessor import PreprocessedInput


@dataclass
class ConversationContext:
    """
    Container for all context relevant to a conversation turn.
    
    Attributes:
        system_prompt: The system prompt for the AI.
        memory_context: Retrieved relevant memories.
        recent_messages: Recent conversation history.
        user_input: The current preprocessed user input.
        additional_context: Any additional context (e.g., from tools).
    """

    system_prompt: str
    memory_context: str
    recent_messages: list[dict[str, str]]
    user_input: PreprocessedInput
    additional_context: dict[str, Any] = field(default_factory=dict)
    
    def to_messages(self) -> list[dict[str, str]]:
        """
        Convert context to OpenAI message format.
        
        Returns:
            list[dict]: Messages ready for API call.
        """
        messages = []
        
        # System message with memory context
        system_content = self.system_prompt
        if self.memory_context:
            system_content += f"\n\n--- User Context ---\n{self.memory_context}"
        
        messages.append({
            "role": "system",
            "content": system_content,
        })
        
        # Recent conversation history
        messages.extend(self.recent_messages)
        
        # Current user message
        messages.append({
            "role": "user",
            "content": self.user_input.cleaned_text,
        })
        
        return messages
    
    def estimate_tokens(self) -> int:
        """
        Estimate the number of tokens in the context.
        
        Uses rough approximation of 4 characters per token.
        """
        messages = self.to_messages()
        total_chars = sum(len(m["content"]) for m in messages)
        return total_chars // 4


class ContextManager(LoggerMixin):
    """
    Manages conversation context and prompt construction.
    
    Responsibilities:
    - Build system prompts with personality
    - Retrieve and inject relevant memories
    - Manage context window size
    - Track conversation state
    
    Args:
        settings: Application settings.
        memory_manager: Memory manager for context retrieval.
    """

    DEFAULT_SYSTEM_PROMPT = """You are a helpful, friendly personal assistant. Your primary goals are:

1. Be helpful and provide accurate information
2. Remember important details about the user
3. Help manage tasks, reminders, and schedules
4. Be concise but thorough in your responses
5. Ask clarifying questions when needed

You have access to the user's personal context and memories to provide personalized assistance.
When the user asks you to remember something, acknowledge it and I'll store it in memory.
When performing tasks like setting reminders, confirm the details back to the user.

Current date and time: {current_datetime}
"""

    def __init__(
        self,
        settings: Settings,
        memory_manager: MemoryManager,
        custom_system_prompt: str | None = None,
    ) -> None:
        self.settings = settings
        self.memory_manager = memory_manager
        self._system_prompt = custom_system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self._session_context: dict[str, Any] = {}

    async def build_context(
        self,
        preprocessed_input: PreprocessedInput,
        include_memories: bool = True,
    ) -> ConversationContext:
        """
        Build the full conversation context for an API call.
        
        Args:
            preprocessed_input: The preprocessed user input.
            include_memories: Whether to retrieve relevant memories.
            
        Returns:
            ConversationContext: Complete context for the turn.
        """
        from datetime import datetime
        
        # Build system prompt with current time
        system_prompt = self._system_prompt.format(
            current_datetime=datetime.now().strftime("%A, %B %d, %Y at %I:%M %p"),
        )
        
        # Retrieve relevant memories
        memory_context = ""
        if include_memories:
            memory_context = await self.memory_manager.retrieve_context(
                query=preprocessed_input.cleaned_text,
                include_recent_conversation=False,  # We handle this separately
            )
        
        # Get recent conversation history
        recent_messages = await self.memory_manager.get_recent_conversation(
            limit=self.settings.conversation_history_length * 2
        )
        
        context = ConversationContext(
            system_prompt=system_prompt,
            memory_context=memory_context,
            recent_messages=recent_messages,
            user_input=preprocessed_input,
        )
        
        # Check token limits and trim if necessary
        context = self._trim_context(context)
        
        self.logger.debug(
            f"Built context: ~{context.estimate_tokens()} tokens, "
            f"{len(recent_messages)} history messages"
        )
        
        return context

    def _trim_context(self, context: ConversationContext) -> ConversationContext:
        """
        Trim context to fit within token limits.
        
        Prioritizes:
        1. System prompt (always kept)
        2. Current user message (always kept)
        3. Recent messages (trimmed oldest first)
        4. Memory context (trimmed if needed)
        """
        max_tokens = self.settings.max_context_tokens
        
        while context.estimate_tokens() > max_tokens:
            # First, try trimming history
            if len(context.recent_messages) > 2:
                context.recent_messages = context.recent_messages[2:]  # Remove oldest pair
                continue
            
            # Then, trim memory context
            if context.memory_context:
                lines = context.memory_context.split("\n")
                if len(lines) > 1:
                    context.memory_context = "\n".join(lines[:-1])
                    continue
                else:
                    context.memory_context = ""
                    continue
            
            # If we can't trim anymore, break
            break
        
        return context

    def set_session_context(self, key: str, value: Any) -> None:
        """
        Set a session-level context variable.
        
        Useful for tracking state within a conversation session.
        """
        self._session_context[key] = value

    def get_session_context(self, key: str, default: Any = None) -> Any:
        """Get a session-level context variable."""
        return self._session_context.get(key, default)

    def clear_session_context(self) -> None:
        """Clear all session context."""
        self._session_context.clear()

    def update_system_prompt(self, prompt: str) -> None:
        """Update the system prompt."""
        self._system_prompt = prompt
        self.logger.info("Updated system prompt")

    def add_personality_trait(self, trait: str) -> None:
        """Add a personality trait to the system prompt."""
        self._system_prompt += f"\n- {trait}"

    async def extract_facts_from_response(
        self,
        user_message: str,
        assistant_response: str,
    ) -> list[str]:
        """
        Extract facts to remember from a conversation exchange.
        
        This is a simple heuristic approach. In production, you might
        use the LLM to extract facts more intelligently.
        """
        facts: list[str] = []
        
        # Check for explicit "remember" requests
        remember_patterns = [
            r"my (?:name is|wife|husband|daughter|son|pet|dog|cat|favorite) (?:is )?(\w+)",
            r"i (?:am|live in|work at|work for) (\w+)",
            r"(?:remember|note|save) that (.+)",
        ]
        
        import re
        message_lower = user_message.lower()
        
        for pattern in remember_patterns:
            match = re.search(pattern, message_lower)
            if match:
                # Extract the fact in a more complete form
                facts.append(user_message)
                break
        
        return facts
