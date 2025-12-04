"""
Screen reader that captures and OCRs the active screen content.

Uses macOS Vision framework for fast, accurate OCR without external dependencies.
"""

import asyncio
import subprocess
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


class ScreenReader:
    """Reads text content from the screen using screenshot + OCR."""
    
    def __init__(self, cache_duration: float = 5.0):
        """
        Initialize screen reader.
        
        Args:
            cache_duration: How long to cache OCR results (seconds)
        """
        self.cache_duration = cache_duration
        self._last_capture: Optional[datetime] = None
        self._cached_text: Optional[str] = None
        self._temp_dir = tempfile.mkdtemp(prefix="agentic_screen_")
    
    async def capture_screen(self, region: Optional[tuple] = None) -> Optional[str]:
        """
        Capture screenshot and return the file path.
        
        Args:
            region: Optional (x, y, width, height) to capture specific region
            
        Returns:
            Path to screenshot file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = os.path.join(self._temp_dir, f"screen_{timestamp}.png")
        
        try:
            if region:
                x, y, w, h = region
                # Capture specific region
                cmd = ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", screenshot_path]
            else:
                # Capture entire screen (primary display)
                cmd = ["screencapture", "-x", "-D", "1", screenshot_path]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.wait()
            
            if os.path.exists(screenshot_path):
                return screenshot_path
        except Exception as e:
            print(f"Screenshot error: {e}")
        
        return None
    
    async def ocr_image_vision(self, image_path: str) -> Optional[str]:
        """
        Extract text from image using macOS Vision framework.
        
        This is fast and accurate, no external dependencies needed.
        """
        # Swift script using Vision framework
        swift_script = f'''
import Cocoa
import Vision

let imagePath = "{image_path}"
guard let image = NSImage(contentsOfFile: imagePath) else {{
    print("ERROR: Could not load image")
    exit(1)
}}

guard let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {{
    print("ERROR: Could not create CGImage")
    exit(1)
}}

let request = VNRecognizeTextRequest {{ request, error in
    guard let observations = request.results as? [VNRecognizedTextObservation] else {{
        print("ERROR: No results")
        return
    }}
    
    for observation in observations {{
        if let topCandidate = observation.topCandidates(1).first {{
            print(topCandidate.string)
        }}
    }}
}}

request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {{
    try handler.perform([request])
}} catch {{
    print("ERROR: \\(error)")
}}
'''
        
        try:
            # Write swift script to temp file
            swift_path = os.path.join(self._temp_dir, "ocr.swift")
            with open(swift_path, "w") as f:
                f.write(swift_script)
            
            # Compile and run
            process = await asyncio.create_subprocess_exec(
                "swift", swift_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                text = stdout.decode("utf-8").strip()
                return text if text else None
            else:
                # Fallback to simpler method
                return await self.ocr_image_simple(image_path)
                
        except Exception as e:
            print(f"Vision OCR error: {e}")
            return await self.ocr_image_simple(image_path)
    
    async def ocr_image_simple(self, image_path: str) -> Optional[str]:
        """
        Simpler OCR using shortcuts/automator or tesseract if available.
        """
        # Try tesseract first if installed
        try:
            process = await asyncio.create_subprocess_exec(
                "tesseract", image_path, "stdout", "-l", "eng",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                return stdout.decode("utf-8").strip()
        except FileNotFoundError:
            pass
        
        # Fallback: Use macOS built-in text recognition via shortcuts
        # This requires a Shortcut named "OCR Image" to be created
        try:
            process = await asyncio.create_subprocess_exec(
                "shortcuts", "run", "OCR Image", "-i", image_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            if process.returncode == 0:
                return stdout.decode("utf-8").strip()
        except Exception:
            pass
        
        return None
    
    async def read_screen(self, use_cache: bool = True) -> Optional[str]:
        """
        Capture screen and extract text.
        
        Args:
            use_cache: Whether to use cached result if recent
            
        Returns:
            Extracted text from screen
        """
        # Check cache
        if use_cache and self._cached_text and self._last_capture:
            elapsed = (datetime.now() - self._last_capture).total_seconds()
            if elapsed < self.cache_duration:
                return self._cached_text
        
        # Capture screen
        screenshot_path = await self.capture_screen()
        if not screenshot_path:
            return None
        
        try:
            # Try tesseract first (faster and more reliable)
            text = await self.ocr_image_simple(screenshot_path)
            
            # If that fails, try Vision framework
            if not text:
                text = await self.ocr_image_vision(screenshot_path)
            
            # Update cache
            self._cached_text = text
            self._last_capture = datetime.now()
            
            return text
        finally:
            # Clean up screenshot
            try:
                os.remove(screenshot_path)
            except:
                pass
    
    async def read_active_window(self) -> Optional[str]:
        """
        Capture and OCR only the active window.
        
        Returns:
            Extracted text from active window
        """
        # Get active window bounds using AppleScript
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            tell frontApp
                set winPos to position of front window
                set winSize to size of front window
            end tell
        end tell
        return (item 1 of winPos) & "," & (item 2 of winPos) & "," & (item 1 of winSize) & "," & (item 2 of winSize)
        '''
        
        try:
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                parts = stdout.decode().strip().split(",")
                if len(parts) == 4:
                    x, y, w, h = map(int, parts)
                    screenshot_path = await self.capture_screen(region=(x, y, w, h))
                    if screenshot_path:
                        try:
                            text = await self.ocr_image_vision(screenshot_path)
                            return text
                        finally:
                            try:
                                os.remove(screenshot_path)
                            except:
                                pass
        except Exception as e:
            print(f"Window capture error: {e}")
        
        # Fallback to full screen
        return await self.read_screen()
    
    async def find_text_on_screen(self, search_text: str) -> bool:
        """
        Check if specific text appears on screen.
        
        Args:
            search_text: Text to search for
            
        Returns:
            True if text found
        """
        screen_text = await self.read_screen()
        if screen_text:
            return search_text.lower() in screen_text.lower()
        return False
    
    async def get_screen_summary(self, max_chars: int = 2000) -> str:
        """
        Get a summarized view of screen content.
        
        Args:
            max_chars: Maximum characters to return
            
        Returns:
            Screen content summary
        """
        text = await self.read_active_window()
        
        if not text:
            return "Could not read screen content."
        
        # Clean up text
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        cleaned = "\n".join(lines)
        
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars] + "\n... (truncated)"
        
        return cleaned
    
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
_screen_reader: Optional[ScreenReader] = None


def get_screen_reader() -> ScreenReader:
    """Get or create the global screen reader instance."""
    global _screen_reader
    if _screen_reader is None:
        _screen_reader = ScreenReader()
    return _screen_reader


async def read_screen_content() -> Optional[str]:
    """Convenience function to read screen content."""
    reader = get_screen_reader()
    return await reader.read_active_window()
