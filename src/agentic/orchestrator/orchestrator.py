"""
Task orchestrator that routes input to appropriate skills.

The orchestrator is the central coordinator for handling user requests.
"""

from typing import Any

from agentic.core.logging import LoggerMixin
from agentic.preprocessing.preprocessor import IntentType, PreprocessedInput
from agentic.skills.base import BaseSkill, SkillPriority, SkillResult


class TaskOrchestrator(LoggerMixin):
    """
    Orchestrates task execution by routing to appropriate skills.
    
    The orchestrator:
    - Maintains a registry of available skills
    - Matches user intents to capable skills
    - Executes skills and handles results
    - Supports skill prioritization
    
    Usage:
        orchestrator = TaskOrchestrator()
        orchestrator.register_skill(ReminderSkill())
        orchestrator.register_skill(NotesSkill())
        
        result = await orchestrator.process(preprocessed_input)
    """

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}
        self._intent_skills: dict[IntentType, list[BaseSkill]] = {}
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize all registered skills."""
        if self._initialized:
            return
        
        for skill in self._skills.values():
            try:
                await skill.setup()
                self.logger.info(f"Initialized skill: {skill.name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize skill {skill.name}: {e}")
        
        self._initialized = True

    async def shutdown(self) -> None:
        """Shutdown all skills and release resources."""
        for skill in self._skills.values():
            try:
                await skill.teardown()
            except Exception as e:
                self.logger.error(f"Error shutting down skill {skill.name}: {e}")
        
        self._initialized = False

    def register_skill(self, skill: BaseSkill) -> None:
        """
        Register a skill with the orchestrator.
        
        Args:
            skill: The skill instance to register.
        """
        if skill.name in self._skills:
            self.logger.warning(f"Overwriting existing skill: {skill.name}")
        
        self._skills[skill.name] = skill
        
        # Index by supported intents
        for intent in skill.supported_intents:
            if intent not in self._intent_skills:
                self._intent_skills[intent] = []
            self._intent_skills[intent].append(skill)
            # Sort by priority
            self._intent_skills[intent].sort(
                key=lambda s: s.priority.value
            )
        
        self.logger.info(
            f"Registered skill: {skill.name} "
            f"(intents: {[i.value for i in skill.supported_intents]})"
        )

    def unregister_skill(self, skill_name: str) -> bool:
        """
        Unregister a skill.
        
        Args:
            skill_name: Name of the skill to unregister.
            
        Returns:
            bool: True if skill was unregistered.
        """
        if skill_name not in self._skills:
            return False
        
        skill = self._skills.pop(skill_name)
        
        # Remove from intent index
        for intent in skill.supported_intents:
            if intent in self._intent_skills:
                self._intent_skills[intent] = [
                    s for s in self._intent_skills[intent] if s.name != skill_name
                ]
        
        self.logger.info(f"Unregistered skill: {skill_name}")
        return True

    async def process(
        self,
        preprocessed: PreprocessedInput,
    ) -> tuple[bool, SkillResult | None]:
        """
        Process user input through the skill system.
        
        Args:
            preprocessed: The preprocessed user input.
            
        Returns:
            tuple[bool, SkillResult | None]: 
                - bool: True if a skill handled the input
                - SkillResult: The result from the skill, or None
        """
        # Get skills that support this intent
        candidate_skills = self._intent_skills.get(preprocessed.intent, [])
        
        # Also check skills for GENERAL intent as fallback
        if preprocessed.intent != IntentType.GENERAL:
            candidate_skills = candidate_skills + self._intent_skills.get(
                IntentType.GENERAL, []
            )
        
        # Add all skills and let them decide via can_handle
        all_skills = list(self._skills.values())
        
        # Check each skill
        for skill in candidate_skills:
            try:
                if await skill.can_handle(preprocessed):
                    self.logger.info(f"Skill '{skill.name}' handling intent: {preprocessed.intent.value}")
                    
                    # Check if confirmation is required
                    if skill.requires_confirmation:
                        # In a full implementation, you'd handle confirmation flow
                        pass
                    
                    result = await skill.execute(preprocessed)
                    return True, result
            except Exception as e:
                self.logger.error(f"Error in skill {skill.name}: {e}")
                continue
        
        # Fallback: check all skills
        for skill in all_skills:
            if skill in candidate_skills:
                continue  # Already checked
            
            try:
                if await skill.can_handle(preprocessed):
                    self.logger.info(f"Fallback skill '{skill.name}' handling input")
                    result = await skill.execute(preprocessed)
                    return True, result
            except Exception as e:
                self.logger.error(f"Error in skill {skill.name}: {e}")
                continue
        
        # No skill could handle the input
        return False, None

    def get_skill(self, name: str) -> BaseSkill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        """
        List all registered skills.
        
        Returns:
            list[dict]: Skill information.
        """
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "intents": [i.value for i in skill.supported_intents],
                "priority": skill.priority.name,
            }
            for skill in self._skills.values()
        ]

    def get_capabilities(self) -> str:
        """
        Get a human-readable description of capabilities.
        
        Returns:
            str: Description of what the assistant can do.
        """
        capabilities = ["I can help you with:"]
        
        for skill in self._skills.values():
            capabilities.append(f"• {skill.description}")
        
        return "\n".join(capabilities)
