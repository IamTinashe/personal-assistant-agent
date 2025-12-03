"""
Speech-to-text handler using OpenAI Whisper.

Provides voice input capability for the assistant.
"""

import tempfile
from pathlib import Path
from typing import BinaryIO

from agentic.core.config import Settings, WhisperModel
from agentic.core.exceptions import VoiceError
from agentic.core.logging import LoggerMixin


class SpeechToText(LoggerMixin):
    """
    Speech-to-text converter using OpenAI Whisper.
    
    Supports:
    - Local Whisper model
    - OpenAI Whisper API (fallback)
    - Multiple audio formats
    
    Args:
        settings: Application settings.
        use_local: Whether to use local Whisper model (default: True).
    """

    def __init__(
        self,
        settings: Settings,
        use_local: bool = True,
    ) -> None:
        self.settings = settings
        self.use_local = use_local
        self._model = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the Whisper model."""
        if self._initialized:
            return
        
        if self.use_local:
            try:
                import whisper
                
                model_name = self.settings.whisper_model.value
                self.logger.info(f"Loading Whisper model: {model_name}")
                self._model = whisper.load_model(model_name)
                self.logger.info("Whisper model loaded")
            except ImportError:
                self.logger.warning(
                    "Local Whisper not available. Install with: pip install openai-whisper"
                )
                self.use_local = False
            except Exception as e:
                self.logger.error(f"Failed to load Whisper model: {e}")
                self.use_local = False
        
        self._initialized = True

    async def transcribe(
        self,
        audio_path: Path | str,
        language: str | None = None,
    ) -> str:
        """
        Transcribe audio file to text.
        
        Args:
            audio_path: Path to the audio file.
            language: Optional language code (e.g., 'en', 'es').
            
        Returns:
            str: Transcribed text.
            
        Raises:
            VoiceError: If transcription fails.
        """
        audio_path = Path(audio_path)
        
        if not audio_path.exists():
            raise VoiceError(f"Audio file not found: {audio_path}")
        
        if self.use_local and self._model:
            return await self._transcribe_local(audio_path, language)
        else:
            return await self._transcribe_api(audio_path, language)

    async def _transcribe_local(
        self,
        audio_path: Path,
        language: str | None = None,
    ) -> str:
        """Transcribe using local Whisper model."""
        import asyncio
        
        try:
            # Run in executor since Whisper is CPU-bound
            loop = asyncio.get_event_loop()
            
            options = {}
            if language:
                options["language"] = language
            
            result = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(str(audio_path), **options),
            )
            
            text = result["text"].strip()
            self.logger.debug(f"Transcribed: {text[:100]}...")
            return text
            
        except Exception as e:
            raise VoiceError(f"Local transcription failed: {e}")

    async def _transcribe_api(
        self,
        audio_path: Path,
        language: str | None = None,
    ) -> str:
        """Transcribe using OpenAI Whisper API."""
        from openai import AsyncOpenAI
        
        try:
            client = AsyncOpenAI(
                api_key=self.settings.openai_api_key.get_secret_value()
            )
            
            with open(audio_path, "rb") as audio_file:
                response = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                )
            
            text = response.text.strip()
            self.logger.debug(f"API transcribed: {text[:100]}...")
            return text
            
        except Exception as e:
            raise VoiceError(f"API transcription failed: {e}")

    async def transcribe_bytes(
        self,
        audio_data: bytes,
        format: str = "wav",
        language: str | None = None,
    ) -> str:
        """
        Transcribe audio from bytes.
        
        Args:
            audio_data: Raw audio bytes.
            format: Audio format (wav, mp3, etc.).
            language: Optional language code.
            
        Returns:
            str: Transcribed text.
        """
        # Write to temp file
        with tempfile.NamedTemporaryFile(
            suffix=f".{format}",
            delete=False,
        ) as f:
            f.write(audio_data)
            temp_path = Path(f.name)
        
        try:
            return await self.transcribe(temp_path, language)
        finally:
            temp_path.unlink(missing_ok=True)

    async def close(self) -> None:
        """Release resources."""
        self._model = None
        self._initialized = False
