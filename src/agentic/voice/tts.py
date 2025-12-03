"""
Text-to-speech handler with multiple engine support.

Provides voice output capability for the assistant.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import BinaryIO

from agentic.core.config import Settings, TTSEngine
from agentic.core.exceptions import VoiceError
from agentic.core.logging import LoggerMixin


class TextToSpeech(LoggerMixin):
    """
    Text-to-speech converter with multiple engine support.
    
    Supported engines:
    - pyttsx3: Local, offline TTS
    - ElevenLabs: High-quality cloud TTS (requires API key)
    
    Args:
        settings: Application settings.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._engine = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the TTS engine."""
        if self._initialized:
            return
        
        engine_type = self.settings.tts_engine
        
        if engine_type == TTSEngine.PYTTSX3:
            await self._init_pyttsx3()
        elif engine_type == TTSEngine.ELEVENLABS:
            await self._init_elevenlabs()
        else:
            self.logger.warning(f"Unknown TTS engine: {engine_type}, falling back to pyttsx3")
            await self._init_pyttsx3()
        
        self._initialized = True

    async def _init_pyttsx3(self) -> None:
        """Initialize pyttsx3 engine."""
        try:
            import pyttsx3
            
            self._engine = pyttsx3.init()
            self._engine_type = TTSEngine.PYTTSX3
            
            # Configure voice
            self._engine.setProperty("rate", 175)  # Speed
            self._engine.setProperty("volume", 0.9)
            
            self.logger.info("pyttsx3 TTS engine initialized")
        except ImportError:
            raise VoiceError(
                "pyttsx3 not installed. Install with: pip install pyttsx3"
            )

    async def _init_elevenlabs(self) -> None:
        """Initialize ElevenLabs API."""
        # ElevenLabs doesn't need initialization, just mark ready
        self._engine_type = TTSEngine.ELEVENLABS
        self.logger.info("ElevenLabs TTS engine initialized")

    async def speak(self, text: str) -> None:
        """
        Speak the given text.
        
        Args:
            text: Text to speak.
            
        Raises:
            VoiceError: If speech synthesis fails.
        """
        if not self._initialized:
            await self.initialize()
        
        if self._engine_type == TTSEngine.PYTTSX3:
            await self._speak_pyttsx3(text)
        elif self._engine_type == TTSEngine.ELEVENLABS:
            await self._speak_elevenlabs(text)

    async def _speak_pyttsx3(self, text: str) -> None:
        """Speak using pyttsx3."""
        loop = asyncio.get_event_loop()
        
        try:
            await loop.run_in_executor(
                None,
                lambda: self._pyttsx3_say(text),
            )
        except Exception as e:
            raise VoiceError(f"pyttsx3 speech failed: {e}")

    def _pyttsx3_say(self, text: str) -> None:
        """Synchronous pyttsx3 speak."""
        self._engine.say(text)
        self._engine.runAndWait()

    async def _speak_elevenlabs(self, text: str) -> None:
        """Speak using ElevenLabs API."""
        try:
            import httpx
            
            # You would need to configure ElevenLabs API key in settings
            # This is a placeholder implementation
            self.logger.warning("ElevenLabs requires API key configuration")
            
            # Fallback to pyttsx3 for now
            await self._init_pyttsx3()
            await self._speak_pyttsx3(text)
            
        except Exception as e:
            raise VoiceError(f"ElevenLabs speech failed: {e}")

    async def synthesize_to_file(
        self,
        text: str,
        output_path: Path | str,
    ) -> Path:
        """
        Synthesize speech to an audio file.
        
        Args:
            text: Text to synthesize.
            output_path: Path for the output audio file.
            
        Returns:
            Path: Path to the created audio file.
        """
        output_path = Path(output_path)
        
        if not self._initialized:
            await self.initialize()
        
        if self._engine_type == TTSEngine.PYTTSX3:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._pyttsx3_save(text, output_path),
            )
        else:
            raise VoiceError(f"File synthesis not supported for {self._engine_type}")
        
        return output_path

    def _pyttsx3_save(self, text: str, output_path: Path) -> None:
        """Save speech to file using pyttsx3."""
        self._engine.save_to_file(text, str(output_path))
        self._engine.runAndWait()

    async def get_voices(self) -> list[dict[str, str]]:
        """
        Get available voices.
        
        Returns:
            list[dict]: Available voice information.
        """
        if not self._initialized:
            await self.initialize()
        
        if self._engine_type == TTSEngine.PYTTSX3:
            voices = self._engine.getProperty("voices")
            return [
                {
                    "id": voice.id,
                    "name": voice.name,
                    "languages": voice.languages,
                }
                for voice in voices
            ]
        
        return []

    async def set_voice(self, voice_id: str) -> None:
        """Set the voice to use."""
        if self._engine_type == TTSEngine.PYTTSX3 and self._engine:
            self._engine.setProperty("voice", voice_id)

    async def set_rate(self, rate: int) -> None:
        """Set speech rate (words per minute)."""
        if self._engine_type == TTSEngine.PYTTSX3 and self._engine:
            self._engine.setProperty("rate", rate)

    async def close(self) -> None:
        """Release resources."""
        if self._engine_type == TTSEngine.PYTTSX3 and self._engine:
            self._engine.stop()
        self._engine = None
        self._initialized = False
