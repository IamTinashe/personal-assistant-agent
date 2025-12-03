"""
OpenAI API client wrapper with embedding and chat completion support.

Provides a unified interface for OpenAI API interactions.
"""

import asyncio
from typing import Any, AsyncGenerator

import openai
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from agentic.core.config import Settings
from agentic.core.exceptions import (
    ContextTooLongError,
    EmbeddingError,
    OpenAIError,
    RateLimitError,
)
from agentic.core.logging import LoggerMixin


class OpenAIClient(LoggerMixin):
    """
    Async OpenAI API client with retry logic and error handling.
    
    Features:
    - Async chat completions
    - Streaming support
    - Embedding generation
    - Automatic retry with exponential backoff
    - Token counting estimation
    
    Args:
        settings: Application settings with OpenAI configuration.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: AsyncOpenAI | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if self._initialized:
            return
        
        self._client = AsyncOpenAI(
            api_key=self.settings.openai_api_key.get_secret_value(),
        )
        self._initialized = True
        self.logger.info("OpenAI client initialized")

    async def close(self) -> None:
        """Close the OpenAI client."""
        if self._client:
            await self._client.close()
            self._initialized = False
            self.logger.info("OpenAI client closed")

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate a chat completion.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Optional model override.
            temperature: Optional temperature override.
            max_tokens: Optional max tokens override.
            **kwargs: Additional parameters for the API.
            
        Returns:
            str: The assistant's response text.
            
        Raises:
            OpenAIError: If the API call fails.
        """
        self._ensure_initialized()
        
        try:
            response = await self._client.chat.completions.create(
                model=model or self.settings.openai_model,
                messages=messages,
                temperature=temperature or self.settings.openai_temperature,
                max_tokens=max_tokens or self.settings.openai_max_tokens,
                **kwargs,
            )
            
            content = response.choices[0].message.content or ""
            
            self.logger.debug(
                f"Chat completion: {response.usage.prompt_tokens} prompt, "
                f"{response.usage.completion_tokens} completion tokens"
            )
            
            return content
            
        except openai.RateLimitError as e:
            self.logger.warning(f"Rate limit hit: {e}")
            raise RateLimitError(str(e))
        except openai.BadRequestError as e:
            if "context_length_exceeded" in str(e).lower():
                raise ContextTooLongError(str(e))
            raise OpenAIError(str(e))
        except openai.APIError as e:
            self.logger.error(f"OpenAI API error: {e}")
            raise OpenAIError(str(e))

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """
        Generate a streaming chat completion.
        
        Args:
            messages: List of message dictionaries.
            model: Optional model override.
            temperature: Optional temperature override.
            max_tokens: Optional max tokens override.
            **kwargs: Additional parameters.
            
        Yields:
            str: Chunks of the response as they arrive.
        """
        self._ensure_initialized()
        
        try:
            stream = await self._client.chat.completions.create(
                model=model or self.settings.openai_model,
                messages=messages,
                temperature=temperature or self.settings.openai_temperature,
                max_tokens=max_tokens or self.settings.openai_max_tokens,
                stream=True,
                **kwargs,
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                    
        except openai.RateLimitError as e:
            raise RateLimitError(str(e))
        except openai.APIError as e:
            raise OpenAIError(str(e))

    async def generate_embedding(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """
        Generate an embedding vector for text.
        
        Args:
            text: The text to embed.
            model: Optional embedding model override.
            
        Returns:
            list[float]: The embedding vector.
            
        Raises:
            EmbeddingError: If embedding generation fails.
        """
        self._ensure_initialized()
        
        try:
            response = await self._client.embeddings.create(
                model=model or self.settings.openai_embedding_model,
                input=text,
            )
            
            return response.data[0].embedding
            
        except openai.APIError as e:
            self.logger.error(f"Embedding error: {e}")
            raise EmbeddingError(str(e))

    async def generate_embeddings_batch(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed.
            model: Optional embedding model override.
            
        Returns:
            list[list[float]]: List of embedding vectors.
        """
        self._ensure_initialized()
        
        try:
            response = await self._client.embeddings.create(
                model=model or self.settings.openai_embedding_model,
                input=texts,
            )
            
            # Sort by index to maintain order
            embeddings = sorted(response.data, key=lambda x: x.index)
            return [e.embedding for e in embeddings]
            
        except openai.APIError as e:
            self.logger.error(f"Batch embedding error: {e}")
            raise EmbeddingError(str(e))

    async def chat_with_retry(
        self,
        messages: list[dict[str, str]],
        max_retries: int = 3,
        **kwargs: Any,
    ) -> str:
        """
        Chat completion with automatic retry on failure.
        
        Args:
            messages: List of message dictionaries.
            max_retries: Maximum number of retry attempts.
            **kwargs: Additional parameters.
            
        Returns:
            str: The assistant's response.
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self.chat_completion(messages, **kwargs)
            except RateLimitError as e:
                last_error = e
                wait_time = e.retry_after or (2 ** attempt)
                self.logger.warning(f"Rate limited, waiting {wait_time}s (attempt {attempt + 1})")
                await asyncio.sleep(wait_time)
            except OpenAIError as e:
                last_error = e
                wait_time = 2 ** attempt
                self.logger.warning(f"API error, retrying in {wait_time}s (attempt {attempt + 1})")
                await asyncio.sleep(wait_time)
        
        raise last_error or OpenAIError("Max retries exceeded")

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in text.
        
        Uses a rough approximation. For accurate counts, use tiktoken.
        
        Args:
            text: The text to estimate tokens for.
            
        Returns:
            int: Estimated token count.
        """
        # Rough approximation: ~4 characters per token
        return len(text) // 4

    def _ensure_initialized(self) -> None:
        """Ensure the client is initialized."""
        if not self._initialized:
            raise OpenAIError("OpenAI client not initialized. Call initialize() first.")
