"""
Audio recording utilities for voice input.
"""

import asyncio
import wave
from io import BytesIO
from pathlib import Path
from typing import Callable

from agentic.core.exceptions import VoiceError
from agentic.core.logging import LoggerMixin


class AudioRecorder(LoggerMixin):
    """
    Audio recorder for capturing voice input.
    
    Uses sounddevice for cross-platform audio recording.
    
    Args:
        sample_rate: Audio sample rate (default: 16000 Hz).
        channels: Number of audio channels (default: 1 - mono).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._recording: bool = False
        self._audio_data: list = []

    async def record(
        self,
        duration: float,
        callback: Callable[[bytes], None] | None = None,
    ) -> bytes:
        """
        Record audio for a fixed duration.
        
        Args:
            duration: Recording duration in seconds.
            callback: Optional callback for audio chunks.
            
        Returns:
            bytes: Recorded audio data as WAV.
        """
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            raise VoiceError(
                "sounddevice not installed. Install with: pip install sounddevice"
            )
        
        self.logger.info(f"Recording for {duration} seconds...")
        
        # Record audio
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.int16,
        )
        sd.wait()
        
        self.logger.info("Recording complete")
        
        # Convert to WAV bytes
        return self._to_wav(audio)

    async def record_until_silence(
        self,
        silence_threshold: float = 0.01,
        silence_duration: float = 1.0,
        max_duration: float = 30.0,
    ) -> bytes:
        """
        Record until silence is detected.
        
        Args:
            silence_threshold: Volume threshold for silence detection.
            silence_duration: Duration of silence to stop recording.
            max_duration: Maximum recording duration.
            
        Returns:
            bytes: Recorded audio data as WAV.
        """
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError:
            raise VoiceError("sounddevice not installed")
        
        self._recording = True
        self._audio_data = []
        silence_samples = 0
        silence_samples_threshold = int(silence_duration * self.sample_rate)
        
        def audio_callback(indata, frames, time, status):
            if status:
                self.logger.warning(f"Audio callback status: {status}")
            
            if not self._recording:
                raise sd.CallbackStop()
            
            self._audio_data.append(indata.copy())
            
            # Check for silence
            volume = np.abs(indata).mean()
            nonlocal silence_samples
            
            if volume < silence_threshold:
                silence_samples += frames
            else:
                silence_samples = 0
            
            if silence_samples >= silence_samples_threshold:
                self._recording = False
        
        self.logger.info("Recording (speak, then pause to finish)...")
        
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                callback=audio_callback,
            ):
                start_time = asyncio.get_event_loop().time()
                
                while self._recording:
                    await asyncio.sleep(0.1)
                    
                    if asyncio.get_event_loop().time() - start_time > max_duration:
                        self._recording = False
                        break
        except sd.CallbackStop:
            pass
        
        self.logger.info("Recording complete")
        
        # Combine audio chunks
        import numpy as np
        audio = np.concatenate(self._audio_data) if self._audio_data else np.array([])
        
        return self._to_wav(audio)

    def _to_wav(self, audio_data) -> bytes:
        """Convert numpy array to WAV bytes."""
        import numpy as np
        
        buffer = BytesIO()
        
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        return buffer.getvalue()

    async def save_to_file(self, audio_data: bytes, path: Path | str) -> Path:
        """
        Save audio data to a file.
        
        Args:
            audio_data: WAV audio bytes.
            path: Output file path.
            
        Returns:
            Path: Path to the saved file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "wb") as f:
            f.write(audio_data)
        
        return path

    def stop_recording(self) -> None:
        """Stop current recording."""
        self._recording = False
