"""
Vision analyzer that uses GPT-4 Vision to understand screen content.

Can analyze screenshots, summarize what's happening, and answer questions
about the visual content.
"""

import asyncio
import base64
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import tempfile

from openai import AsyncOpenAI


class VisionAnalyzer:
    """Analyzes screen content using GPT-4 Vision."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize vision analyzer.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client: Optional[AsyncOpenAI] = None
        self._temp_dir = tempfile.mkdtemp(prefix="agentic_vision_")
        
        # Cache for recent analysis
        self._last_analysis: Optional[str] = None
        self._last_image_hash: Optional[str] = None
        self._last_analysis_time: Optional[datetime] = None
        self._cache_duration = 10.0  # seconds
    
    @property
    def client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client
    
    async def capture_screen(self) -> Optional[str]:
        """Capture screenshot and return path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(self._temp_dir, f"screen_{timestamp}.png")
        
        try:
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-D", "1", screenshot_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()
            
            if os.path.exists(screenshot_path):
                return screenshot_path
        except Exception as e:
            print(f"Screenshot error: {e}")
        
        return None
    
    async def capture_active_window(self) -> Optional[str]:
        """Capture only the active window."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(self._temp_dir, f"window_{timestamp}.png")
        
        try:
            # Capture the frontmost window
            process = await asyncio.create_subprocess_exec(
                "screencapture", "-x", "-l", 
                # Get window ID of frontmost window
                screenshot_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()
            
            if os.path.exists(screenshot_path):
                return screenshot_path
        except Exception:
            pass
        
        # Fallback to full screen
        return await self.capture_screen()
    
    def _encode_image(self, image_path: str) -> str:
        """Encode image to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    async def analyze_screen(
        self,
        question: Optional[str] = None,
        detail: str = "auto",
    ) -> str:
        """
        Analyze the current screen content.
        
        Args:
            question: Specific question about the screen (optional)
            detail: Image detail level ('low', 'high', 'auto')
            
        Returns:
            Analysis or answer about the screen content
        """
        # Capture screen
        screenshot_path = await self.capture_screen()
        if not screenshot_path:
            return "Could not capture screen."
        
        try:
            return await self._analyze_image(screenshot_path, question, detail)
        finally:
            # Clean up
            try:
                os.remove(screenshot_path)
            except:
                pass
    
    async def _analyze_image(
        self,
        image_path: str,
        question: Optional[str] = None,
        detail: str = "auto",
    ) -> str:
        """Analyze an image with GPT-4 Vision."""
        
        # Encode image
        base64_image = self._encode_image(image_path)
        
        # Build prompt based on whether there's a question
        if question:
            system_prompt = """You are an AI assistant that can see the user's screen. 
You are helpful, accurate, and concise. Answer questions about what you see.
Focus on the relevant parts of the screen to answer the question.
If you see code, you can explain it. If you see an error, you can help debug it.
If you see a website, you can describe what's on it."""
            
            user_prompt = f"Looking at my screen, {question}"
        else:
            system_prompt = """You are an AI assistant that can see the user's screen.
Provide a helpful summary of what's currently displayed.
Focus on:
1. What application/website is open
2. What the user appears to be doing
3. Any notable content, errors, or information visible
4. Anything that might need attention

Be concise but informative. Use bullet points for clarity."""
            
            user_prompt = "What's happening on my screen right now? Give me a quick summary."
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",  # GPT-4 Vision model
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}",
                                    "detail": detail,
                                },
                            },
                        ],
                    },
                ],
                max_tokens=1000,
            )
            
            return response.choices[0].message.content or "Could not analyze screen."
            
        except Exception as e:
            return f"Error analyzing screen: {e}"
    
    async def summarize_screen(self) -> str:
        """Get a quick summary of what's on screen."""
        return await self.analyze_screen(
            question=None,
            detail="low",  # Use low detail for faster/cheaper summary
        )
    
    async def answer_about_screen(self, question: str) -> str:
        """Answer a specific question about what's on screen."""
        return await self.analyze_screen(
            question=question,
            detail="high",  # Use high detail for specific questions
        )
    
    async def explain_error(self) -> str:
        """Look for and explain any errors on screen."""
        return await self.analyze_screen(
            question="Do you see any errors, warnings, or issues on the screen? If so, explain what they mean and how to fix them.",
            detail="high",
        )
    
    async def explain_code(self) -> str:
        """Explain any code visible on screen."""
        return await self.analyze_screen(
            question="What code is visible on screen? Explain what it does and any issues you notice.",
            detail="high",
        )
    
    async def read_and_summarize(self) -> str:
        """Read all text on screen and provide a summary."""
        return await self.analyze_screen(
            question="Read all the text visible on screen and provide a comprehensive summary of the content.",
            detail="high",
        )
    
    async def get_context_for_help(self) -> str:
        """Analyze screen to understand context for providing help."""
        return await self.analyze_screen(
            question="""Analyze this screen to understand the context:
1. What application/tool is being used?
2. What is the user trying to do?
3. Are there any errors or issues visible?
4. What would be the most helpful information to provide?

Provide a brief context summary that would help another AI assist this user.""",
            detail="auto",
        )
    
    def cleanup(self):
        """Clean up temporary files."""
        try:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        except:
            pass
    
    def __del__(self):
        self.cleanup()


# Singleton instance
_vision_analyzer: Optional[VisionAnalyzer] = None


def get_vision_analyzer() -> VisionAnalyzer:
    """Get or create the global vision analyzer instance."""
    global _vision_analyzer
    if _vision_analyzer is None:
        _vision_analyzer = VisionAnalyzer()
    return _vision_analyzer


async def analyze_screen(question: Optional[str] = None) -> str:
    """Convenience function to analyze screen content."""
    analyzer = get_vision_analyzer()
    return await analyzer.analyze_screen(question)
