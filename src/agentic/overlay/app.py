"""
Floating overlay assistant - a small window that stays on top of all windows.

Features:
- Always-on-top floating widget
- Minimizable to a small icon
- Global hotkey (Cmd+Shift+Space) to show/hide
- Voice input support with always-listening mode
- Clipboard watching with auto-suggestions
"""

import asyncio
import sys
import threading
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import (
    Qt,
    QPoint,
    QSize,
    QTimer,
    pyqtSignal,
    QThread,
    QObject,
    QPropertyAnimation,
    QEasingCurve,
)
from PyQt6.QtGui import (
    QFont,
    QIcon,
    QCursor,
    QKeySequence,
    QShortcut,
    QAction,
    QPixmap,
    QPainter,
    QColor,
    QBrush,
    QClipboard,
)
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QLineEdit,
    QPushButton,
    QLabel,
    QFrame,
    QSystemTrayIcon,
    QMenu,
    QSizeGrip,
    QGraphicsDropShadowEffect,
)


class AsyncWorker(QObject):
    """Worker to run async operations in a thread."""
    
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, coro_func, *args, **kwargs):
        super().__init__()
        self.coro_func = coro_func
        self.args = args
        self.kwargs = kwargs
    
    def run(self):
        """Run the async function."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.coro_func(*self.args, **self.kwargs)
            )
            loop.close()
            self.finished.emit(str(result) if result else "")
        except Exception as e:
            self.error.emit(str(e))


class FloatingButton(QPushButton):
    """Minimized floating button."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.setText("🤖")
        self.setFont(QFont("Arial", 20))
        self.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2
                );
                border: none;
                border-radius: 25px;
                color: white;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #764ba2, stop:1 #667eea
                );
            }
            QPushButton:pressed {
                background: #5a67d8;
            }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Add shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
        
        # For dragging
        self._drag_pos = None
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class ChatOverlay(QWidget):
    """Main chat overlay window."""
    
    response_ready = pyqtSignal(str)
    
    def __init__(self, assistant=None):
        super().__init__()
        self.assistant = assistant
        self._drag_pos = None
        self._worker = None
        self._thread = None
        
        self._setup_ui()
        self._setup_window()
        
        self.response_ready.connect(self._display_response)
    
    def _setup_window(self):
        """Configure window properties."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(320, 200)
        self.resize(380, 450)
        
        # Position at bottom-right of screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 400, screen.height() - 520)
    
    def _setup_ui(self):
        """Build the UI."""
        # Main container with rounded corners
        self.container = QFrame(self)
        self.container.setObjectName("container")
        self.container.setStyleSheet("""
            #container {
                background-color: rgba(30, 30, 40, 0.95);
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        
        # Add shadow to container
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 8)
        self.container.setGraphicsEffect(shadow)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.addWidget(self.container)
        
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Header
        header = self._create_header()
        container_layout.addWidget(header)
        
        # Chat area
        self.chat_area = QTextEdit()
        self.chat_area.setReadOnly(True)
        self.chat_area.setStyleSheet("""
            QTextEdit {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 13px;
                padding: 12px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.2);
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)
        self.chat_area.setPlaceholderText("Ask me anything...")
        container_layout.addWidget(self.chat_area)
        
        # Input area
        input_area = self._create_input_area()
        container_layout.addWidget(input_area)
        
        # Size grip
        grip = QSizeGrip(self)
        grip.setStyleSheet("background: transparent;")
    
    def _create_header(self) -> QFrame:
        """Create the header with title and controls."""
        header = QFrame()
        header.setFixedHeight(44)
        header.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }
        """)
        
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 8, 0)
        
        # Title
        title = QLabel("🤖 Assistant")
        title.setStyleSheet("""
            color: white;
            font-size: 14px;
            font-weight: bold;
        """)
        layout.addWidget(title)
        
        # Status indicator
        self.status_label = QLabel("● Ready")
        self.status_label.setStyleSheet("color: #4ade80; font-size: 11px;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # Control buttons
        for text, action, color in [
            ("−", self.minimize, "#fbbf24"),
            ("×", self.close, "#f87171"),
        ]:
            btn = QPushButton(text)
            btn.setFixedSize(28, 28)
            btn.clicked.connect(action)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {color};
                    font-size: 18px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.1);
                    border-radius: 14px;
                }}
            """)
            layout.addWidget(btn)
        
        return header
    
    def _create_input_area(self) -> QFrame:
        """Create the input area with text field and buttons."""
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.05);
                border-bottom-left-radius: 16px;
                border-bottom-right-radius: 16px;
            }
        """)
        
        layout = QHBoxLayout(input_frame)
        layout.setContentsMargins(12, 8, 12, 12)
        layout.setSpacing(8)
        
        # Text input
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask anything... (Enter to send)")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                padding: 10px 16px;
                color: white;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #667eea;
            }
        """)
        self.input_field.returnPressed.connect(self._send_message)
        layout.addWidget(self.input_field)
        
        # Voice button
        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedSize(40, 40)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.3);
            }
            QPushButton:pressed {
                background: #667eea;
            }
        """)
        self.voice_btn.clicked.connect(self._voice_input)
        layout.addWidget(self.voice_btn)
        
        # Send button
        send_btn = QPushButton("→")
        send_btn.setFixedSize(40, 40)
        send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2
                );
                border: none;
                border-radius: 20px;
                color: white;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #764ba2, stop:1 #667eea
                );
            }
        """)
        send_btn.clicked.connect(self._send_message)
        layout.addWidget(send_btn)
        
        return input_frame
    
    def _send_message(self):
        """Send the message to the assistant."""
        message = self.input_field.text().strip()
        if not message:
            return
        
        self.input_field.clear()
        self._append_message("You", message, "#667eea")
        self._set_status("thinking", "Thinking...")
        
        if self.assistant:
            self._run_async(self._get_response, message)
        else:
            # Demo mode
            QTimer.singleShot(500, lambda: self._display_response(
                f"I would respond to: '{message}'\n\n"
                "(Connect the assistant for real responses)"
            ))
    
    async def _get_response(self, message: str) -> str:
        """Get response from assistant."""
        try:
            response = await self.assistant.chat(message, stream=False)
            # Handle different response types
            if hasattr(response, '__aiter__'):
                # It's an async generator, collect all chunks
                chunks = []
                async for chunk in response:
                    chunks.append(chunk)
                return ''.join(chunks)
            return str(response) if response else "I couldn't generate a response."
        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"Error: {e}"
    
    def _run_async(self, coro_func, *args, **kwargs):
        """Run an async function in a thread."""
        self._thread = QThread()
        self._worker = AsyncWorker(coro_func, *args, **kwargs)
        self._worker.moveToThread(self._thread)
        
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_async_finished)
        self._worker.error.connect(self._on_async_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        
        self._thread.start()
    
    def _on_async_finished(self, result: str):
        """Handle async completion."""
        self.response_ready.emit(result)
    
    def _on_async_error(self, error: str):
        """Handle async error."""
        self._display_response(f"Error: {error}")
    
    def _display_response(self, response: str):
        """Display the assistant's response."""
        self._append_message("Assistant", response, "#4ade80")
        self._set_status("ready", "Ready")
    
    def _append_message(self, sender: str, message: str, color: str):
        """Append a message to the chat area."""
        html = f"""
        <div style="margin-bottom: 12px;">
            <span style="color: {color}; font-weight: bold; font-size: 11px;">
                {sender}
            </span>
            <div style="color: #e0e0e0; margin-top: 4px; line-height: 1.4;">
                {message.replace(chr(10), '<br>')}
            </div>
        </div>
        """
        self.chat_area.append(html)
        # Scroll to bottom
        scrollbar = self.chat_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _set_status(self, status: str, text: str):
        """Update status indicator."""
        colors = {
            "ready": "#4ade80",
            "thinking": "#fbbf24",
            "listening": "#f87171",
            "error": "#ef4444",
        }
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(f"color: {colors.get(status, '#9ca3af')}; font-size: 11px;")
    
    def _voice_input(self):
        """Handle voice input."""
        self._set_status("listening", "Listening...")
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: #ef4444;
                border: none;
                border-radius: 20px;
                font-size: 16px;
            }
        """)
        
        if self.assistant:
            # TODO: Implement voice recording
            QTimer.singleShot(2000, self._stop_voice)
        else:
            QTimer.singleShot(1000, self._stop_voice)
    
    def _stop_voice(self):
        """Stop voice recording."""
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                font-size: 16px;
            }
            QPushButton:hover {
                background: rgba(102, 126, 234, 0.3);
            }
        """)
        self._set_status("ready", "Ready")
    
    def minimize(self):
        """Minimize to floating button."""
        self.hide()
        if hasattr(self, 'on_minimize'):
            self.on_minimize()
    
    def mousePressEvent(self, event):
        """Handle mouse press for dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Only allow dragging from header area
            if event.position().y() < 50:
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging."""
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class OverlayApp:
    """Main overlay application controller with hotkeys, clipboard watching, and voice."""
    
    def __init__(self, assistant=None, enable_hotkey: bool = True):
        self.assistant = assistant
        self.enable_hotkey = enable_hotkey
        self.app = None
        self.chat_overlay = None
        self.floating_btn = None
        self.tray_icon = None
        self._hotkey_listener = None
        self._clipboard_watcher = None
        self._last_clipboard = ""
        self._voice_listening = False
    
    def run(self):
        """Run the overlay application."""
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        
        # Create chat overlay
        self.chat_overlay = ChatOverlay(self.assistant)
        self.chat_overlay.on_minimize = self._show_floating_btn
        
        # Create floating button
        self.floating_btn = FloatingButton()
        self.floating_btn.clicked.connect(self._show_chat)
        
        # Position floating button
        screen = QApplication.primaryScreen().geometry()
        self.floating_btn.move(screen.width() - 70, screen.height() - 120)
        
        # Create system tray with extended menu
        self._setup_tray()
        
        # Setup global hotkey (Cmd+Shift+Space on Mac) - optional
        if self.enable_hotkey:
            self._setup_global_hotkey()
        
        # Setup clipboard watching
        self._setup_clipboard_watcher()
        
        # Show chat overlay initially
        self.chat_overlay.show()
        
        # Global hotkey hint
        print("💡 Overlay running!")
        print("   ⌘+Shift+Space - Show/hide chat")
        print("   Clipboard watching enabled")
        print("   Close from system tray to quit.")
        
        return self.app.exec()
    
    def _setup_global_hotkey(self):
        """Setup global hotkey to toggle overlay."""
        try:
            # Note: pynput requires Accessibility permissions on macOS
            # System Preferences > Security & Privacy > Privacy > Accessibility
            from pynput import keyboard
            
            # Define hotkey combination: Cmd+Shift+Space
            HOTKEY = {keyboard.Key.cmd, keyboard.Key.shift, keyboard.Key.space}
            current_keys = set()
            
            def on_press(key):
                current_keys.add(key)
                if HOTKEY.issubset(current_keys):
                    # Use QTimer to safely call from another thread
                    QTimer.singleShot(0, self._toggle_overlay)
            
            def on_release(key):
                current_keys.discard(key)
            
            self._hotkey_listener = keyboard.Listener(
                on_press=on_press,
                on_release=on_release,
            )
            self._hotkey_listener.start()
            print("   ✓ Global hotkey registered: ⌘+Shift+Space")
        except ImportError:
            print("   ⚠ pynput not installed - global hotkey disabled")
        except Exception as e:
            print(f"   ⚠ Global hotkey disabled (grant Accessibility permission): {e}")
    
    def _setup_clipboard_watcher(self):
        """Setup clipboard monitoring for auto-suggestions."""
        clipboard = QApplication.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_change)
        self._last_clipboard = clipboard.text()
        print("   ✓ Clipboard watching enabled")
    
    def _on_clipboard_change(self):
        """Handle clipboard content change."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        # Ignore if same as last or empty
        if not text or text == self._last_clipboard:
            return
        
        self._last_clipboard = text
        
        # Only suggest for meaningful text (not too short, not too long)
        if 10 < len(text) < 2000:
            # Show suggestion bubble
            self._show_clipboard_suggestion(text)
    
    def _show_clipboard_suggestion(self, text: str):
        """Show a suggestion based on clipboard content."""
        # Truncate for display
        preview = text[:100] + "..." if len(text) > 100 else text
        preview = preview.replace('\n', ' ')
        
        # Show notification via tray
        if self.tray_icon:
            self.tray_icon.showMessage(
                "📋 Clipboard Detected",
                f"Ask about: \"{preview}\"",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        
        # If chat is visible, offer to explain
        if self.chat_overlay.isVisible():
            self.chat_overlay._append_message(
                "System",
                f"📋 Copied text detected. Ask me to explain, summarize, or analyze it!",
                "#9ca3af",
            )
    
    def _toggle_overlay(self):
        """Toggle overlay visibility."""
        if self.chat_overlay.isVisible():
            self.chat_overlay.minimize()
        else:
            self._show_chat()
    
    def _setup_tray(self):
        """Setup system tray icon with extended menu."""
        self.tray_icon = QSystemTrayIcon(self.app)
        
        # Create icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QBrush(QColor("#667eea")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 32, 32)
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Arial", 14))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "🤖")
        painter.end()
        
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("AI Assistant (⌘+Shift+Space)")
        
        # Tray menu
        menu = QMenu()
        
        show_action = QAction("Show Chat (⌘+Shift+Space)", self.app)
        show_action.triggered.connect(self._show_chat)
        menu.addAction(show_action)
        
        menu.addSeparator()
        
        # Voice listening toggle
        self.voice_action = QAction("🎤 Always Listen: OFF", self.app)
        self.voice_action.triggered.connect(self._toggle_voice_listening)
        menu.addAction(self.voice_action)
        
        # Clipboard watching toggle
        self.clipboard_action = QAction("📋 Clipboard Watch: ON", self.app)
        self.clipboard_action.setCheckable(True)
        self.clipboard_action.setChecked(True)
        self.clipboard_action.triggered.connect(self._toggle_clipboard_watch)
        menu.addAction(self.clipboard_action)
        
        menu.addSeparator()
        
        # Quick actions
        explain_action = QAction("Explain Clipboard", self.app)
        explain_action.triggered.connect(lambda: self._quick_action("explain"))
        menu.addAction(explain_action)
        
        summarize_action = QAction("Summarize Clipboard", self.app)
        summarize_action.triggered.connect(lambda: self._quick_action("summarize"))
        menu.addAction(summarize_action)
        
        menu.addSeparator()
        
        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.messageClicked.connect(self._show_chat)
        self.tray_icon.show()
    
    def _toggle_voice_listening(self):
        """Toggle always-listening voice mode."""
        self._voice_listening = not self._voice_listening
        
        if self._voice_listening:
            self.voice_action.setText("🎤 Always Listen: ON")
            self.tray_icon.showMessage(
                "Voice Mode",
                "Always-listening mode enabled. Say 'Hey Assistant' to activate.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            # TODO: Start voice listener thread
        else:
            self.voice_action.setText("🎤 Always Listen: OFF")
            # TODO: Stop voice listener thread
    
    def _toggle_clipboard_watch(self, checked: bool):
        """Toggle clipboard watching."""
        self.clipboard_action.setText(f"📋 Clipboard Watch: {'ON' if checked else 'OFF'}")
        
        clipboard = QApplication.clipboard()
        if checked:
            clipboard.dataChanged.connect(self._on_clipboard_change)
        else:
            try:
                clipboard.dataChanged.disconnect(self._on_clipboard_change)
            except:
                pass
    
    def _quick_action(self, action: str):
        """Execute a quick action on clipboard content."""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        if not text:
            self.tray_icon.showMessage(
                "No Content",
                "Clipboard is empty",
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )
            return
        
        self._show_chat()
        
        if action == "explain":
            self.chat_overlay.input_field.setText(f"Explain this: {text[:500]}")
        elif action == "summarize":
            self.chat_overlay.input_field.setText(f"Summarize this: {text[:500]}")
        
        self.chat_overlay._send_message()
    
    def _tray_activated(self, reason):
        """Handle tray icon activation."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_overlay()
    
    def _show_chat(self):
        """Show the chat overlay."""
        self.floating_btn.hide()
        self.chat_overlay.show()
        self.chat_overlay.raise_()
        self.chat_overlay.activateWindow()
        self.chat_overlay.input_field.setFocus()
    
    def _show_floating_btn(self):
        """Show the floating button."""
        self.floating_btn.show()
    
    def _quit_app(self):
        """Clean up and quit."""
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.app.quit()


def main():
    """Run the overlay in demo mode."""
    app = OverlayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
