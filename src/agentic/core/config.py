"""
Configuration management using Pydantic Settings.

Centralized configuration for all components with environment variable support.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorStoreType(str, Enum):
    """Supported vector store backends."""

    FAISS = "faiss"
    PINECONE = "pinecone"


class TTSEngine(str, Enum):
    """Supported text-to-speech engines."""

    PYTTSX3 = "pyttsx3"
    COQUI = "coqui"
    ELEVENLABS = "elevenlabs"


class WhisperModel(str, Enum):
    """Available Whisper model sizes."""

    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI Configuration
    openai_api_key: SecretStr = Field(..., description="OpenAI API key")
    openai_model: str = Field(
        default="gpt-4-turbo-preview",
        description="OpenAI model for chat completions",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI model for embeddings",
    )
    openai_max_tokens: int = Field(default=4096, ge=1, le=128000)
    openai_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Vector Store Configuration
    vector_store_type: VectorStoreType = Field(default=VectorStoreType.FAISS)
    vector_store_path: Path = Field(default=Path("./data/vector_store"))
    vector_dimension: int = Field(default=1536, description="Embedding dimension size")

    # Pinecone Configuration (optional)
    pinecone_api_key: SecretStr | None = Field(default=None)
    pinecone_environment: str = Field(default="us-east-1")
    pinecone_index_name: str = Field(default="agentic-memory")

    # Database Configuration
    database_url: str = Field(default="sqlite+aiosqlite:///./data/agentic.db")

    # Logging Configuration
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )
    log_file: Path = Field(default=Path("./logs/agentic.log"))

    # Voice Configuration
    enable_voice_input: bool = Field(default=False)
    enable_voice_output: bool = Field(default=False)
    whisper_model: WhisperModel = Field(default=WhisperModel.BASE)
    tts_engine: TTSEngine = Field(default=TTSEngine.PYTTSX3)

    # API Server Configuration
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_reload: bool = Field(default=True)

    # Memory Configuration
    max_context_tokens: int = Field(default=2000, ge=100, le=100000)
    memory_retrieval_count: int = Field(default=5, ge=1, le=20)
    conversation_history_length: int = Field(default=10, ge=1, le=50)

    # Integration APIs
    google_calendar_credentials_path: Path | None = Field(default=None)
    gmail_credentials_path: Path | None = Field(default=None)

    # Security
    encrypt_local_data: bool = Field(default=False)
    encryption_key: SecretStr | None = Field(default=None)

    @field_validator("vector_store_path", "log_file", mode="before")
    @classmethod
    def convert_to_path(cls, v: str | Path) -> Path:
        """Convert string paths to Path objects."""
        return Path(v) if isinstance(v, str) else v

    @field_validator("google_calendar_credentials_path", "gmail_credentials_path", mode="before")
    @classmethod
    def convert_optional_path(cls, v: str | Path | None) -> Path | None:
        """Convert optional string paths to Path objects."""
        if v is None:
            return None
        return Path(v) if isinstance(v, str) else v

    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create data directory for database
        db_path = self.database_url.split("///")[-1]
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings: Application settings singleton.
    """
    return Settings()
