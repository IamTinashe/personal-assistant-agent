"""
Input preprocessor with entity extraction and intent detection.

Cleans user input and extracts structured information.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from agentic.core.logging import LoggerMixin


class IntentType(str, Enum):
    """Detected user intent types."""

    # Task-related intents
    SET_REMINDER = "set_reminder"
    CREATE_TASK = "create_task"
    LIST_TASKS = "list_tasks"
    COMPLETE_TASK = "complete_task"
    DELETE_TASK = "delete_task"
    
    # Calendar intents
    CREATE_EVENT = "create_event"
    LIST_EVENTS = "list_events"
    CHECK_AVAILABILITY = "check_availability"
    
    # Note intents
    CREATE_NOTE = "create_note"
    SEARCH_NOTES = "search_notes"
    
    # Information intents
    QUESTION = "question"
    SEARCH = "search"
    DEFINE = "define"
    
    # Conversation intents
    GREETING = "greeting"
    FAREWELL = "farewell"
    THANKS = "thanks"
    HELP = "help"
    
    # General
    GENERAL = "general"
    UNKNOWN = "unknown"


@dataclass
class ExtractedEntity:
    """Represents an extracted entity from text."""

    entity_type: str
    value: Any
    raw_text: str
    start_pos: int
    end_pos: int
    confidence: float = 1.0


@dataclass
class PreprocessedInput:
    """
    Result of input preprocessing.
    
    Contains cleaned text, detected intent, and extracted entities.
    """

    original_text: str
    cleaned_text: str
    intent: IntentType
    intent_confidence: float
    entities: list[ExtractedEntity] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_entity(self, entity_type: str) -> ExtractedEntity | None:
        """Get the first entity of a specific type."""
        for entity in self.entities:
            if entity.entity_type == entity_type:
                return entity
        return None
    
    def get_entities(self, entity_type: str) -> list[ExtractedEntity]:
        """Get all entities of a specific type."""
        return [e for e in self.entities if e.entity_type == entity_type]


class InputPreprocessor(LoggerMixin):
    """
    Preprocesses user input by cleaning text and extracting entities.
    
    Features:
    - Intent detection using pattern matching
    - Date/time extraction
    - Entity extraction (names, numbers, durations)
    - Text normalization
    """

    # Intent patterns with keywords
    INTENT_PATTERNS: dict[IntentType, list[str]] = {
        IntentType.SET_REMINDER: [
            r"remind\s+me",
            r"set\s+(?:a\s+)?reminder",
            r"don'?t\s+let\s+me\s+forget",
            r"alert\s+me",
        ],
        IntentType.CREATE_TASK: [
            r"add\s+(?:a\s+)?task",
            r"create\s+(?:a\s+)?task",
            r"add\s+to\s+(?:my\s+)?(?:to-?do|list)",
            r"i\s+need\s+to",
        ],
        IntentType.LIST_TASKS: [
            r"(?:show|list|what\s+are)\s+(?:my\s+)?tasks",
            r"(?:show|list)\s+(?:my\s+)?to-?do",
            r"what\s+(?:do\s+i\s+have|is)\s+on\s+my\s+(?:list|plate)",
        ],
        IntentType.COMPLETE_TASK: [
            r"(?:mark|set)\s+.*?\s+(?:as\s+)?(?:done|complete|finished)",
            r"i(?:'ve)?\s+(?:done|finished|completed)",
        ],
        IntentType.CREATE_EVENT: [
            r"schedule\s+(?:a\s+)?(?:meeting|event|appointment)",
            r"add\s+(?:a\s+)?(?:meeting|event|appointment)",
            r"book\s+(?:a\s+)?(?:meeting|room|time)",
        ],
        IntentType.LIST_EVENTS: [
            r"(?:show|what(?:'s)?|list)\s+(?:my\s+)?(?:calendar|schedule|events)",
            r"what\s+(?:do\s+i\s+have|is)\s+(?:on|scheduled)",
        ],
        IntentType.CHECK_AVAILABILITY: [
            r"am\s+i\s+(?:free|available|busy)",
            r"do\s+i\s+have\s+(?:anything|something)",
            r"check\s+(?:my\s+)?availability",
        ],
        IntentType.CREATE_NOTE: [
            r"(?:take|make|create|add)\s+(?:a\s+)?note",
            r"(?:write|jot)\s+(?:this\s+)?down",
            r"remember\s+(?:that|this)",
        ],
        IntentType.SEARCH_NOTES: [
            r"(?:find|search|look\s+for)\s+(?:my\s+)?note",
            r"what\s+did\s+i\s+(?:write|note)",
        ],
        IntentType.QUESTION: [
            r"^(?:what|who|where|when|why|how|which|is|are|can|could|would|will|do|does)\b",
            r"\?$",
        ],
        IntentType.SEARCH: [
            r"(?:search|look\s+up|find|google)",
        ],
        IntentType.DEFINE: [
            r"(?:what\s+is|define|meaning\s+of|explain)",
        ],
        IntentType.GREETING: [
            r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|greetings)",
        ],
        IntentType.FAREWELL: [
            r"^(?:bye|goodbye|see\s+you|talk\s+(?:to\s+you\s+)?later|good\s+night)",
        ],
        IntentType.THANKS: [
            r"(?:thank|thanks|thx|appreciate)",
        ],
        IntentType.HELP: [
            r"(?:help|assist|support|how\s+(?:do|can)\s+(?:i|you))",
            r"what\s+can\s+you\s+do",
        ],
    }

    # Date/time patterns
    TIME_PATTERNS = [
        # Specific times
        (r"(\d{1,2}):(\d{2})\s*(am|pm)?", "specific_time"),
        (r"(\d{1,2})\s*(am|pm)", "hour_time"),
        (r"at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", "at_time"),
        # Relative times
        (r"in\s+(\d+)\s*(minute|hour|day|week|month)s?", "relative_time"),
        (r"(tomorrow|today|tonight|yesterday)", "relative_day"),
        (r"next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month)", "next_period"),
        (r"this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|evening|afternoon|morning)", "this_period"),
    ]

    # Duration patterns
    DURATION_PATTERNS = [
        (r"for\s+(\d+)\s*(minute|hour|day|week)s?", "duration"),
        (r"(\d+)\s*(minute|hour|day|week)s?\s+(?:long|duration)", "duration"),
    ]

    def __init__(self) -> None:
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for efficiency."""
        self._intent_patterns = {
            intent: [re.compile(p, re.IGNORECASE) for p in patterns]
            for intent, patterns in self.INTENT_PATTERNS.items()
        }
        self._time_patterns = [
            (re.compile(p, re.IGNORECASE), t) for p, t in self.TIME_PATTERNS
        ]
        self._duration_patterns = [
            (re.compile(p, re.IGNORECASE), t) for p, t in self.DURATION_PATTERNS
        ]

    def preprocess(self, text: str) -> PreprocessedInput:
        """
        Preprocess user input.
        
        Args:
            text: Raw user input text.
            
        Returns:
            PreprocessedInput: Processed input with intent and entities.
        """
        # Clean text
        cleaned = self._clean_text(text)
        
        # Detect intent
        intent, confidence = self._detect_intent(cleaned)
        
        # Extract entities
        entities = self._extract_entities(text, cleaned)
        
        result = PreprocessedInput(
            original_text=text,
            cleaned_text=cleaned,
            intent=intent,
            intent_confidence=confidence,
            entities=entities,
        )
        
        self.logger.debug(
            f"Preprocessed: intent={intent.value} ({confidence:.2f}), "
            f"entities={len(entities)}"
        )
        
        return result

    def _clean_text(self, text: str) -> str:
        """Clean and normalize input text."""
        # Remove extra whitespace
        cleaned = " ".join(text.split())
        
        # Remove leading/trailing whitespace
        cleaned = cleaned.strip()
        
        return cleaned

    def _detect_intent(self, text: str) -> tuple[IntentType, float]:
        """
        Detect the user's intent from text.
        
        Returns:
            tuple[IntentType, float]: Detected intent and confidence score.
        """
        text_lower = text.lower()
        
        matches: list[tuple[IntentType, float]] = []
        
        for intent, patterns in self._intent_patterns.items():
            for pattern in patterns:
                if pattern.search(text_lower):
                    # Calculate confidence based on pattern specificity
                    confidence = 0.8 if len(pattern.pattern) > 20 else 0.6
                    matches.append((intent, confidence))
                    break
        
        if not matches:
            return IntentType.GENERAL, 0.5
        
        # Return highest confidence match
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0]

    def _extract_entities(self, original: str, cleaned: str) -> list[ExtractedEntity]:
        """Extract entities from text."""
        entities: list[ExtractedEntity] = []
        
        # Extract date/time entities
        entities.extend(self._extract_datetime(original))
        
        # Extract duration entities
        entities.extend(self._extract_duration(original))
        
        # Extract quoted strings (often task names or note content)
        entities.extend(self._extract_quoted(original))
        
        # Extract numbers
        entities.extend(self._extract_numbers(original))
        
        return entities

    def _extract_datetime(self, text: str) -> list[ExtractedEntity]:
        """Extract date/time entities from text."""
        entities: list[ExtractedEntity] = []
        now = datetime.now()
        
        for pattern, pattern_type in self._time_patterns:
            for match in pattern.finditer(text):
                try:
                    parsed_dt = self._parse_time_match(match, pattern_type, now)
                    if parsed_dt:
                        entities.append(ExtractedEntity(
                            entity_type="datetime",
                            value=parsed_dt,
                            raw_text=match.group(0),
                            start_pos=match.start(),
                            end_pos=match.end(),
                        ))
                except Exception:
                    continue
        
        # Try general date parsing as fallback
        try:
            # Look for date-like strings
            date_pattern = re.compile(
                r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
            )
            for match in date_pattern.finditer(text):
                try:
                    parsed = date_parser.parse(match.group(0), fuzzy=False)
                    entities.append(ExtractedEntity(
                        entity_type="date",
                        value=parsed,
                        raw_text=match.group(0),
                        start_pos=match.start(),
                        end_pos=match.end(),
                    ))
                except Exception:
                    continue
        except Exception:
            pass
        
        return entities

    def _parse_time_match(
        self,
        match: re.Match,
        pattern_type: str,
        now: datetime,
    ) -> datetime | None:
        """Parse a regex match into a datetime."""
        groups = match.groups()
        
        if pattern_type == "relative_day":
            day_word = groups[0].lower()
            if day_word == "today":
                return now.replace(hour=9, minute=0, second=0, microsecond=0)
            elif day_word == "tonight":
                return now.replace(hour=20, minute=0, second=0, microsecond=0)
            elif day_word == "tomorrow":
                return (now + timedelta(days=1)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
            elif day_word == "yesterday":
                return (now - timedelta(days=1)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
        
        elif pattern_type == "relative_time":
            amount = int(groups[0])
            unit = groups[1].lower()
            
            if "minute" in unit:
                return now + timedelta(minutes=amount)
            elif "hour" in unit:
                return now + timedelta(hours=amount)
            elif "day" in unit:
                return now + timedelta(days=amount)
            elif "week" in unit:
                return now + timedelta(weeks=amount)
            elif "month" in unit:
                return now + relativedelta(months=amount)
        
        elif pattern_type in ("specific_time", "hour_time", "at_time"):
            hour = int(groups[0])
            minute = int(groups[1]) if groups[1] else 0
            meridiem = groups[-1].lower() if groups[-1] else None
            
            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0
            
            result = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # If time has passed today, assume tomorrow
            if result < now:
                result += timedelta(days=1)
            return result
        
        elif pattern_type == "next_period":
            period = groups[0].lower()
            days_of_week = [
                "monday", "tuesday", "wednesday", "thursday",
                "friday", "saturday", "sunday"
            ]
            
            if period in days_of_week:
                target_day = days_of_week.index(period)
                current_day = now.weekday()
                days_ahead = target_day - current_day
                if days_ahead <= 0:
                    days_ahead += 7
                return (now + timedelta(days=days_ahead)).replace(
                    hour=9, minute=0, second=0, microsecond=0
                )
            elif period == "week":
                return now + timedelta(weeks=1)
            elif period == "month":
                return now + relativedelta(months=1)
        
        return None

    def _extract_duration(self, text: str) -> list[ExtractedEntity]:
        """Extract duration entities from text."""
        entities: list[ExtractedEntity] = []
        
        for pattern, _ in self._duration_patterns:
            for match in pattern.finditer(text):
                amount = int(match.group(1))
                unit = match.group(2).lower()
                
                # Convert to timedelta
                if "minute" in unit:
                    duration = timedelta(minutes=amount)
                elif "hour" in unit:
                    duration = timedelta(hours=amount)
                elif "day" in unit:
                    duration = timedelta(days=amount)
                elif "week" in unit:
                    duration = timedelta(weeks=amount)
                else:
                    continue
                
                entities.append(ExtractedEntity(
                    entity_type="duration",
                    value=duration,
                    raw_text=match.group(0),
                    start_pos=match.start(),
                    end_pos=match.end(),
                ))
        
        return entities

    def _extract_quoted(self, text: str) -> list[ExtractedEntity]:
        """Extract quoted strings from text."""
        entities: list[ExtractedEntity] = []
        
        # Match both single and double quotes
        pattern = re.compile(r'["\']([^"\']+)["\']')
        
        for match in pattern.finditer(text):
            entities.append(ExtractedEntity(
                entity_type="quoted_text",
                value=match.group(1),
                raw_text=match.group(0),
                start_pos=match.start(),
                end_pos=match.end(),
            ))
        
        return entities

    def _extract_numbers(self, text: str) -> list[ExtractedEntity]:
        """Extract standalone numbers from text."""
        entities: list[ExtractedEntity] = []
        
        # Match numbers not part of time patterns
        pattern = re.compile(r"\b(\d+(?:\.\d+)?)\b")
        
        for match in pattern.finditer(text):
            # Skip if this looks like part of a time
            context = text[max(0, match.start() - 10):match.end() + 10]
            if re.search(r"[:\-/]", context):
                continue
            
            value = float(match.group(1))
            if value == int(value):
                value = int(value)
            
            entities.append(ExtractedEntity(
                entity_type="number",
                value=value,
                raw_text=match.group(0),
                start_pos=match.start(),
                end_pos=match.end(),
            ))
        
        return entities
