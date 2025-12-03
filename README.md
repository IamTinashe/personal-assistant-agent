<div align="center">

# 🤖 Agentic

### Personal AI Assistant with Long-Term Memory

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy-lang.org/)

A modular, privacy-focused personal assistant powered by OpenAI's GPT-4 and vector store memory. Build your own Jarvis with natural language understanding, task management, and persistent memory.

[Features](#-features) • [Quick Start](#-quick-start) • [Architecture](#-architecture) • [API Reference](#-api-reference) • [Extending](#-extending-with-custom-skills)

</div>

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **Long-term Memory** | Vector store (FAISS local / Pinecone cloud) remembers conversations, facts, and preferences |
| 🎯 **Smart Task Management** | Natural language reminders, tasks, and notes with date/time parsing |
| 🗣️ **Voice Interface** | Optional Whisper STT and pyttsx3/ElevenLabs TTS |
| 🔌 **Modular Skills** | Plugin architecture for adding custom capabilities |
| 🌐 **REST & WebSocket API** | FastAPI server with streaming support |
| 🖥️ **Rich CLI** | Beautiful terminal interface with real-time streaming |
| 🔒 **Privacy First** | Local-first design, your data stays on your machine |
| 🐳 **Docker Ready** | One-command deployment with Docker Compose |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   CLI       │  │  REST API   │  │  WebSocket  │  │   Voice     │        │
│  │  (Typer)    │  │  (FastAPI)  │  │  Streaming  │  │  (Whisper)  │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────┘
          │                │                │                │
          └────────────────┴────────────────┴────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ASSISTANT CORE                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Input Preprocessor                            │   │
│  │  • Intent Detection (20+ intent types)                               │   │
│  │  • Entity Extraction (dates, times, durations, quoted text)          │   │
│  │  • Text Normalization                                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                       │
│                    ▼                               ▼                        │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │     Task Orchestrator       │  │         Context Manager              │  │
│  │  ┌───────────────────────┐  │  │  • Builds conversation context       │  │
│  │  │  Skill Router         │  │  │  • Retrieves relevant memories       │  │
│  │  │  • Reminder Skill     │  │  │  • Manages token limits              │  │
│  │  │  • Task Skill         │  │  │  • Session state tracking            │  │
│  │  │  • Notes Skill        │  │  └─────────────────────────────────────┘  │
│  │  │  • Custom Skills...   │  │                    │                      │
│  │  └───────────────────────┘  │                    │                      │
│  └──────────────┬──────────────┘                    │                      │
│                 │                                   │                      │
│                 └───────────────┬───────────────────┘                      │
│                                 ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                      Response Generator                              │  │
│  │  • Combines skill results with LLM responses                         │  │
│  │  • Handles streaming output                                          │  │
│  │  • Extracts facts for memory storage                                 │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│   OpenAI Client     │  │   Memory Manager    │  │   Voice Engine      │
│  ┌───────────────┐  │  │  ┌───────────────┐  │  │  ┌───────────────┐  │
│  │ GPT-4 Turbo   │  │  │  │ FAISS Store   │  │  │  │ Whisper STT   │  │
│  │ Embeddings    │  │  │  │ (Local)       │  │  │  │ pyttsx3 TTS   │  │
│  │ Retry Logic   │  │  │  ├───────────────┤  │  │  │ ElevenLabs    │  │
│  │ Streaming     │  │  │  │ Pinecone      │  │  │  │ Audio Record  │  │
│  └───────────────┘  │  │  │ (Cloud)       │  │  │  └───────────────┘  │
└─────────────────────┘  │  └───────────────┘  │  └─────────────────────┘
                         └─────────────────────┘
```

### Data Flow Example

```
User: "Remind me to call my daughter Sarah tomorrow at 6 PM"
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. PREPROCESSING                                            │
│    Intent: SET_REMINDER (confidence: 0.85)                  │
│    Entities:                                                │
│      - datetime: 2024-12-04 18:00:00                       │
│      - task_content: "call my daughter Sarah"               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. ORCHESTRATION                                            │
│    Matched Skill: ReminderSkill                             │
│    Action: Create reminder in local storage                 │
│    Result: Success - reminder ID: abc123                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CONTEXT BUILDING                                         │
│    Retrieved memories: "daughter's name is Sarah" (fact)    │
│    Recent conversation: last 3 exchanges                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. RESPONSE GENERATION                                      │
│    GPT-4 generates natural confirmation                     │
│    "I'll remind you to call Sarah tomorrow at 6 PM."        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. MEMORY STORAGE                                           │
│    Store conversation in vector DB                          │
│    Extract fact: "User has daughter named Sarah"            │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- OpenAI API key
- (Optional) Pinecone API key for cloud vector storage

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic.git
cd agentic

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install with desired features
pip install -e .                  # Core only
pip install -e ".[voice]"         # + Voice support
pip install -e ".[web]"           # + API server
pip install -e ".[cloud]"         # + Pinecone
pip install -e ".[all]"           # Everything
```

### Configuration

```bash
# Copy environment template
cp .env.example .env
```

Edit `.env` with your settings:

```env
# Required
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional - Model Configuration
OPENAI_MODEL=gpt-4-turbo-preview
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_MAX_TOKENS=4096
OPENAI_TEMPERATURE=0.7

# Optional - Vector Store (default: local FAISS)
VECTOR_STORE_TYPE=faiss
# VECTOR_STORE_TYPE=pinecone
# PINECONE_API_KEY=your-pinecone-key
# PINECONE_ENVIRONMENT=us-east-1

# Optional - Voice
ENABLE_VOICE_INPUT=false
ENABLE_VOICE_OUTPUT=false
WHISPER_MODEL=base

# Optional - Logging
LOG_LEVEL=INFO
```

### First Run

```bash
# Start interactive chat
agentic chat

# Or run with a single message
agentic chat "Hello! What can you help me with?"
```

## 💻 Usage Examples

### CLI Interface

```bash
# Interactive mode with streaming
agentic chat

# Single message
agentic chat "Set a reminder for tomorrow at 3pm to call the dentist"

# Voice mode (requires voice dependencies)
agentic chat --voice

# Store a fact
agentic remember "My wife's name is Emily and her birthday is March 15th"

# Search memories
agentic recall "family birthdays"

# Start API server
agentic serve --port 8000
```

### Python SDK

```python
import asyncio
from agentic.app import Assistant

async def main():
    # Using context manager (recommended)
    async with Assistant() as assistant:
        # Basic chat
        response = await assistant.chat("Hello!")
        print(response)
        
        # Streaming response
        async for chunk in await assistant.chat("Tell me a story", stream=True):
            print(chunk, end="", flush=True)
        
        # Memory operations
        await assistant.remember("I prefer dark mode interfaces")
        memories = await assistant.recall("preferences")
        
        # Start new session (clears conversation buffer)
        await assistant.new_session()
        
        # Get statistics
        stats = await assistant.get_stats()
        print(stats)

asyncio.run(main())
```

### Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f agentic

# Stop
docker-compose down
```

## 📡 API Reference

### REST Endpoints

| Endpoint | Method | Description | Request Body |
|----------|--------|-------------|--------------|
| `/` | GET | Health check | - |
| `/health` | GET | Health status | - |
| `/chat` | POST | Send message | `{"message": "...", "stream": false}` |
| `/remember` | POST | Store memory | `{"content": "...", "memory_type": "fact"}` |
| `/recall` | POST | Search memory | `{"query": "...", "limit": 5}` |
| `/session/new` | POST | New session | - |
| `/stats` | GET | Statistics | - |
| `/capabilities` | GET | List capabilities | - |

### WebSocket

Connect to `/ws/chat` for real-time streaming:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'chunk') {
        process.stdout.write(data.content);
    } else if (data.type === 'complete') {
        console.log('\n--- Complete ---');
    }
};

ws.send(JSON.stringify({ message: "Tell me about yourself" }));
```

### cURL Examples

```bash
# Chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it?"}'

# Store memory
curl -X POST http://localhost:8000/remember \
  -H "Content-Type: application/json" \
  -d '{"content": "User lives in San Francisco", "memory_type": "fact"}'

# Search memories
curl -X POST http://localhost:8000/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "location", "limit": 5}'

# Get stats
curl http://localhost:8000/stats
```

## 🔌 Extending with Custom Skills

### Creating a Skill

```python
from agentic.skills.base import BaseSkill, SkillResult, SkillPriority
from agentic.preprocessing import IntentType, PreprocessedInput

class WeatherSkill(BaseSkill):
    """Skill for weather information."""
    
    @property
    def name(self) -> str:
        return "weather"
    
    @property
    def description(self) -> str:
        return "Get current weather and forecasts"
    
    @property
    def supported_intents(self) -> list[IntentType]:
        return [IntentType.QUESTION]
    
    @property
    def priority(self) -> SkillPriority:
        return SkillPriority.HIGH
    
    async def setup(self) -> None:
        """Initialize weather API client."""
        self.api_key = os.getenv("WEATHER_API_KEY")
    
    async def can_handle(self, preprocessed: PreprocessedInput) -> bool:
        """Check if this is a weather question."""
        weather_keywords = ["weather", "temperature", "forecast", "rain", "sunny"]
        text = preprocessed.cleaned_text.lower()
        return any(kw in text for kw in weather_keywords)
    
    async def execute(self, preprocessed: PreprocessedInput) -> SkillResult:
        """Get weather information."""
        # Extract location from entities or use default
        location = self._extract_location(preprocessed) or "San Francisco"
        
        # Call weather API
        weather_data = await self._fetch_weather(location)
        
        return SkillResult(
            success=True,
            message=f"The weather in {location} is {weather_data['condition']} "
                   f"with a temperature of {weather_data['temp']}°F",
            data=weather_data,
            should_respond=True,  # Let LLM enhance the response
        )
    
    async def teardown(self) -> None:
        """Cleanup resources."""
        pass
```

### Registering Skills

```python
# In app.py or your initialization code
from your_skills import WeatherSkill, CalendarSkill, EmailSkill

async def initialize(self):
    # ... existing initialization ...
    
    # Register custom skills
    self._orchestrator.register_skill(WeatherSkill())
    self._orchestrator.register_skill(CalendarSkill())
    self._orchestrator.register_skill(EmailSkill())
```

### Skill Lifecycle

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   setup()    │ ──▶ │  can_handle  │ ──▶ │   execute    │
│ (once)       │     │  (per input) │     │  (if match)  │
└──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
┌──────────────┐                         ┌──────────────┐
│  teardown()  │ ◀────────────────────── │ SkillResult  │
│ (shutdown)   │                         └──────────────┘
└──────────────┘
```

## 🗄️ Memory System

### Memory Types

| Type | Description | Example |
|------|-------------|---------|
| `CONVERSATION` | Chat history | User asked about weather |
| `FACT` | Personal facts | User's daughter is named Sarah |
| `PREFERENCE` | User preferences | Prefers morning meetings |
| `TASK` | Task information | Has meeting at 3pm |
| `NOTE` | User notes | Meeting notes from Dec 3 |
| `CONTEXT` | Session context | Currently discussing project X |

### Memory Operations

```python
# Store different memory types
await memory.store_conversation(user_msg, assistant_msg)
await memory.store_fact("User is allergic to peanuts", importance=0.9)
await memory.store_preference("Prefers formal communication", category="style")
await memory.store_note("Project deadline is Dec 15", title="Project Alpha")

# Retrieve context for a query
context = await memory.retrieve_context(
    query="What do I need to do?",
    k=5,
    memory_types=[MemoryType.TASK, MemoryType.NOTE],
)

# Search with filters
results = await memory.search_memories(
    query="family",
    k=10,
    memory_types=[MemoryType.FACT],
    filter_metadata={"category": "personal"},
)
```

### Vector Store Options

#### FAISS (Local - Default)

```env
VECTOR_STORE_TYPE=faiss
VECTOR_STORE_PATH=./data/vector_store
```

- ✅ Free, no API keys needed
- ✅ Fast for small-medium datasets
- ✅ Full privacy - data stays local
- ❌ Limited scalability

#### Pinecone (Cloud)

```env
VECTOR_STORE_TYPE=pinecone
PINECONE_API_KEY=your-key
PINECONE_ENVIRONMENT=us-east-1
PINECONE_INDEX_NAME=agentic-memory
```

- ✅ Highly scalable
- ✅ Managed infrastructure
- ✅ Advanced filtering
- ❌ Requires API key and costs

## 📁 Project Structure

```
agentic/
├── src/agentic/
│   ├── api/                    # REST API & WebSocket
│   │   ├── __init__.py
│   │   └── server.py           # FastAPI application
│   │
│   ├── core/                   # Core utilities
│   │   ├── __init__.py
│   │   ├── config.py           # Pydantic settings
│   │   ├── exceptions.py       # Custom exceptions
│   │   └── logging.py          # Rich logging setup
│   │
│   ├── llm/                    # LLM integration
│   │   ├── __init__.py
│   │   ├── openai_client.py    # OpenAI API wrapper
│   │   └── response.py         # Response generation
│   │
│   ├── memory/                 # Vector store & memory
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract interfaces
│   │   ├── faiss_store.py      # FAISS implementation
│   │   ├── pinecone_store.py   # Pinecone implementation
│   │   └── manager.py          # High-level memory API
│   │
│   ├── orchestrator/           # Task routing
│   │   ├── __init__.py
│   │   └── orchestrator.py     # Skill coordination
│   │
│   ├── preprocessing/          # Input processing
│   │   ├── __init__.py
│   │   ├── preprocessor.py     # Intent & entity extraction
│   │   └── context.py          # Context building
│   │
│   ├── skills/                 # Built-in skills
│   │   ├── __init__.py
│   │   ├── base.py             # Skill interface
│   │   ├── reminder.py         # Reminder management
│   │   ├── tasks.py            # Task management
│   │   └── notes.py            # Note taking
│   │
│   ├── voice/                  # Voice I/O
│   │   ├── __init__.py
│   │   ├── stt.py              # Speech-to-text
│   │   ├── tts.py              # Text-to-speech
│   │   └── recorder.py         # Audio recording
│   │
│   ├── __init__.py
│   ├── app.py                  # Main Assistant class
│   └── cli.py                  # CLI application
│
├── tests/                      # Test suite
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── test_preprocessor.py
│   ├── test_memory.py
│   └── test_skills.py
│
├── .env.example                # Environment template
├── .gitignore
├── docker-compose.yml          # Docker deployment
├── Dockerfile
├── LICENSE
├── pyproject.toml              # Project configuration
└── README.md
```

## ⚙️ Configuration Reference

### All Environment Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| **OpenAI** |
| `OPENAI_API_KEY` | str | *required* | OpenAI API key |
| `OPENAI_MODEL` | str | `gpt-4-turbo-preview` | Chat completion model |
| `OPENAI_EMBEDDING_MODEL` | str | `text-embedding-3-small` | Embedding model |
| `OPENAI_MAX_TOKENS` | int | `4096` | Max response tokens |
| `OPENAI_TEMPERATURE` | float | `0.7` | Response randomness |
| **Vector Store** |
| `VECTOR_STORE_TYPE` | str | `faiss` | `faiss` or `pinecone` |
| `VECTOR_STORE_PATH` | str | `./data/vector_store` | FAISS storage path |
| `VECTOR_DIMENSION` | int | `1536` | Embedding dimensions |
| **Pinecone** |
| `PINECONE_API_KEY` | str | - | Pinecone API key |
| `PINECONE_ENVIRONMENT` | str | `us-east-1` | Pinecone environment |
| `PINECONE_INDEX_NAME` | str | `agentic-memory` | Index name |
| **Database** |
| `DATABASE_URL` | str | `sqlite+aiosqlite:///./data/agentic.db` | Database connection |
| **Logging** |
| `LOG_LEVEL` | str | `INFO` | Log level |
| `LOG_FILE` | str | `./logs/agentic.log` | Log file path |
| **Voice** |
| `ENABLE_VOICE_INPUT` | bool | `false` | Enable STT |
| `ENABLE_VOICE_OUTPUT` | bool | `false` | Enable TTS |
| `WHISPER_MODEL` | str | `base` | Whisper model size |
| `TTS_ENGINE` | str | `pyttsx3` | TTS engine |
| **API Server** |
| `API_HOST` | str | `0.0.0.0` | Server host |
| `API_PORT` | int | `8000` | Server port |
| **Memory** |
| `MAX_CONTEXT_TOKENS` | int | `2000` | Max context size |
| `MEMORY_RETRIEVAL_COUNT` | int | `5` | Memories per query |
| `CONVERSATION_HISTORY_LENGTH` | int | `10` | Recent exchanges kept |

## 🧪 Development

### Setup Development Environment

```bash
# Install all development dependencies
pip install -e ".[all,dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src/agentic --cov-report=html

# Specific test file
pytest tests/test_memory.py -v

# Run specific test
pytest tests/test_skills.py::TestReminderSkill -v
```

### Code Quality

```bash
# Type checking
mypy src/agentic

# Linting
ruff check src/agentic

# Auto-fix lint issues
ruff check src/agentic --fix

# Format code
black src/agentic

# All checks
make lint  # If using Makefile
```

### Building Documentation

```bash
# Generate API docs (if using mkdocs)
mkdocs serve

# Build static docs
mkdocs build
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `pytest`
5. Run code quality checks: `ruff check . && mypy src/agentic`
6. Commit your changes: `git commit -m 'Add amazing feature'`
7. Push to the branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

### Development Guidelines

- Write tests for new features
- Follow existing code style (enforced by ruff/black)
- Add type hints to all functions
- Document public APIs with docstrings
- Keep skills modular and single-purpose

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [OpenAI](https://openai.com/) for GPT-4 and Whisper
- [FAISS](https://github.com/facebookresearch/faiss) for efficient vector search
- [FastAPI](https://fastapi.tiangolo.com/) for the excellent web framework
- [Rich](https://rich.readthedocs.io/) for beautiful terminal output
- [Typer](https://typer.tiangolo.com/) for CLI framework

---

<div align="center">

**[⬆ Back to Top](#-agentic)**

Made with ❤️ by developers, for developers

</div>
