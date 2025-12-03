"""
Response generator that coordinates LLM responses with context and memory.
"""

from typing import Any, AsyncGenerator

from agentic.core.config import Settings
from agentic.core.logging import LoggerMixin
from agentic.llm.openai_client import OpenAIClient
from agentic.memory.manager import MemoryManager
from agentic.preprocessing.context import ContextManager, ConversationContext
from agentic.preprocessing.preprocessor import PreprocessedInput
from agentic.skills.base import SkillResult


class ResponseGenerator(LoggerMixin):
    """
    Generates responses using the LLM with context awareness.
    
    Responsibilities:
    - Build prompts with relevant context
    - Generate responses using OpenAI
    - Store conversations in memory
    - Handle skill result integration
    
    Args:
        settings: Application settings.
        openai_client: OpenAI client instance.
        memory_manager: Memory manager instance.
        context_manager: Context manager instance.
    """

    def __init__(
        self,
        settings: Settings,
        openai_client: OpenAIClient,
        memory_manager: MemoryManager,
        context_manager: ContextManager,
    ) -> None:
        self.settings = settings
        self.openai = openai_client
        self.memory = memory_manager
        self.context = context_manager

    async def generate_response(
        self,
        preprocessed: PreprocessedInput,
        skill_result: SkillResult | None = None,
        stream: bool = False,
    ) -> str | AsyncGenerator[str, None]:
        """
        Generate a response to user input.
        
        Args:
            preprocessed: The preprocessed user input.
            skill_result: Optional result from a skill execution.
            stream: Whether to stream the response.
            
        Returns:
            str | AsyncGenerator: The response or a stream of chunks.
        """
        # Build context
        context = await self.context.build_context(preprocessed)
        
        # If skill provided a result, enhance the context
        if skill_result and skill_result.response_hint:
            context.additional_context["skill_hint"] = skill_result.response_hint
        
        # Get messages for API
        messages = context.to_messages()
        
        # If skill handled it and has a complete message, use that
        if skill_result and skill_result.success and not skill_result.should_respond:
            response = skill_result.message
        elif skill_result and skill_result.success:
            # Add skill result to context
            messages.append({
                "role": "system",
                "content": f"[Task completed] {skill_result.message}. "
                          f"Confirm this to the user naturally.",
            })
            
            if stream:
                return self._stream_response(messages, preprocessed)
            response = await self.openai.chat_completion(messages)
        else:
            # Normal LLM response
            if stream:
                return self._stream_response(messages, preprocessed)
            response = await self.openai.chat_completion(messages)
        
        # Store conversation in memory
        await self._store_conversation(preprocessed.cleaned_text, response)
        
        return response

    async def _stream_response(
        self,
        messages: list[dict[str, str]],
        preprocessed: PreprocessedInput,
    ) -> AsyncGenerator[str, None]:
        """Stream a response and store it when complete."""
        full_response = ""
        
        async for chunk in self.openai.chat_completion_stream(messages):
            full_response += chunk
            yield chunk
        
        # Store the complete conversation
        await self._store_conversation(preprocessed.cleaned_text, full_response)

    async def _store_conversation(
        self,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Store a conversation exchange in memory."""
        try:
            await self.memory.store_conversation(
                user_message=user_message,
                assistant_response=assistant_response,
            )
            
            # Extract and store any facts mentioned
            facts = await self.context.extract_facts_from_response(
                user_message, assistant_response
            )
            for fact in facts:
                await self.memory.store_fact(fact)
                
        except Exception as e:
            self.logger.warning(f"Failed to store conversation: {e}")

    async def generate_summary(
        self,
        text: str,
        max_length: int = 100,
    ) -> str:
        """
        Generate a summary of the given text.
        
        Args:
            text: Text to summarize.
            max_length: Maximum summary length in words.
            
        Returns:
            str: Summary text.
        """
        messages = [
            {
                "role": "system",
                "content": f"Summarize the following text in {max_length} words or less. "
                          "Be concise and capture the key points.",
            },
            {
                "role": "user",
                "content": text,
            },
        ]
        
        return await self.openai.chat_completion(messages)

    async def extract_entities(
        self,
        text: str,
    ) -> dict[str, Any]:
        """
        Use LLM to extract structured entities from text.
        
        Args:
            text: Text to analyze.
            
        Returns:
            dict: Extracted entities.
        """
        messages = [
            {
                "role": "system",
                "content": """Extract structured information from the text.
Return a JSON object with these fields if present:
- dates: list of date/time references
- people: list of names mentioned
- places: list of locations mentioned
- tasks: list of action items or tasks
- facts: list of factual statements to remember
Only include fields that are present in the text.""",
            },
            {
                "role": "user",
                "content": text,
            },
        ]
        
        response = await self.openai.chat_completion(
            messages,
            temperature=0.1,  # Lower temperature for structured output
        )
        
        try:
            import json
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_response": response}
