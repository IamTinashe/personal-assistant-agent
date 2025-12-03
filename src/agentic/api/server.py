"""
FastAPI server for the Agentic assistant.

Provides REST API and WebSocket endpoints.
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agentic.app import Assistant
from agentic.core.config import get_settings
from agentic.core.logging import get_logger

logger = get_logger("api")

# Global assistant instance
_assistant: Assistant | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global _assistant
    
    logger.info("Starting API server...")
    _assistant = Assistant(get_settings())
    await _assistant.initialize()
    
    yield
    
    logger.info("Shutting down API server...")
    if _assistant:
        await _assistant.shutdown()


app = FastAPI(
    title="Agentic API",
    description="Personal AI Assistant API with memory and task management",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
class ChatRequest(BaseModel):
    """Chat request body."""

    message: str = Field(..., min_length=1, max_length=10000)
    stream: bool = Field(default=False)


class ChatResponse(BaseModel):
    """Chat response body."""

    response: str
    intent: str | None = None


class MemoryRequest(BaseModel):
    """Memory storage request."""

    content: str = Field(..., min_length=1, max_length=5000)
    memory_type: str = Field(default="fact")


class MemoryResponse(BaseModel):
    """Memory response."""

    id: str
    message: str


class SearchRequest(BaseModel):
    """Memory search request."""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)


class SearchResponse(BaseModel):
    """Search response."""

    results: list[dict[str, Any]]


class StatsResponse(BaseModel):
    """Statistics response."""

    memory: dict[str, Any]
    skills: list[dict[str, Any]]


# API Endpoints
@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "agentic"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Send a message to the assistant.
    
    Returns the assistant's response.
    """
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    try:
        response = await _assistant.chat(request.message, stream=False)
        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/remember", response_model=MemoryResponse)
async def remember(request: MemoryRequest) -> MemoryResponse:
    """Store information in memory."""
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    try:
        result = await _assistant.remember(request.content)
        return MemoryResponse(id="stored", message=result)
    except Exception as e:
        logger.error(f"Memory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/recall", response_model=SearchResponse)
async def recall(request: SearchRequest) -> SearchResponse:
    """Search memory for relevant information."""
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    try:
        results = await _assistant.recall(request.query, k=request.limit)
        return SearchResponse(
            results=[{"content": r} for r in results]
        )
    except Exception as e:
        logger.error(f"Recall error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/new")
async def new_session() -> dict[str, str]:
    """Start a new conversation session."""
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    await _assistant.new_session()
    return {"status": "ok", "message": "New session started"}


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """Get assistant statistics."""
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    data = await _assistant.get_stats()
    return StatsResponse(**data)


@app.get("/capabilities")
async def capabilities() -> dict[str, str]:
    """Get assistant capabilities."""
    if not _assistant:
        raise HTTPException(status_code=503, detail="Assistant not initialized")
    
    return {"capabilities": _assistant.get_capabilities()}


# WebSocket endpoint for streaming chat
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for streaming chat.
    
    Send JSON messages: {"message": "your message"}
    Receive JSON responses: {"type": "chunk|complete|error", "content": "..."}
    """
    await websocket.accept()
    
    if not _assistant:
        await websocket.send_json({"type": "error", "content": "Assistant not initialized"})
        await websocket.close()
        return
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get("message", "")
            
            if not message:
                await websocket.send_json({"type": "error", "content": "Empty message"})
                continue
            
            # Stream response
            try:
                response_stream = await _assistant.chat(message, stream=True)
                
                async for chunk in response_stream:
                    await websocket.send_json({"type": "chunk", "content": chunk})
                
                await websocket.send_json({"type": "complete", "content": ""})
                
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
