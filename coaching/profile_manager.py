"""Profile manager — extracts and updates user profile from conversations."""

import json
import structlog

from llm.base import BaseLLMProvider, LLMMessage, LLMResponse
from database.models import UserProfile

logger = structlog.get_logger()

EXTRACT_PROFILE_PROMPT = """Analyse le message suivant de l'utilisateur et extrais toute information relative à son profil fitness.

Retourne UNIQUEMENT un objet JSON valide avec les champs trouvés parmi :
{
  "age": <int ou null>,
  "height_cm": <float ou null>,
  "weight_kg": <float ou null>,
  "sex": <string ou null>,
  "fitness_level": <"debutant"|"intermediaire"|"avance" ou null>,
  "goal": <string ou null>,
  "available_equipment": <string ou null>,
  "training_frequency": <string ou null>,
  "injuries_constraints": <string ou null>,
  "dietary_preferences": <string ou null>,
  "allergies": <string ou null>,
  "food_budget": <string ou null>,
  "lifestyle_rhythm": <string ou null>,
  "wake_up_time": <string ou null>,
  "sleep_time": <string ou null>,
  "extra_info": <string ou null>
}

- Ne mets QUE les champs pour lesquels tu trouves une information dans le message.
- Si aucune information de profil n'est détectée, retourne {}.
- Ne rajoute aucun texte, explication ou commentaire, juste le JSON.

Message de l'utilisateur :
\"\"\"
{user_message}
\"\"\"
"""


class ProfileManager:
    """Extract profile data from user messages and keep the profile up to date."""

    def __init__(self, llm: BaseLLMProvider):
        self.llm = llm

    async def extract_profile_updates(self, user_message: str) -> dict:
        """Use LLM to extract profile fields from a user message."""
        prompt = EXTRACT_PROFILE_PROMPT.replace("{user_message}", user_message)
        messages = [LLMMessage(role="user", content=prompt)]

        try:
            response: LLMResponse = await self.llm.chat(messages, temperature=0.1)
            # Parse JSON from response
            text = response.content.strip()
            # Handle markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]
            data = json.loads(text)
            # Filter out null values
            return {k: v for k, v in data.items() if v is not None}
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning("Failed to extract profile data", error=str(e))
            return {}

    def check_profile_completeness(self, profile: UserProfile | dict | None) -> tuple[bool, list[str]]:
        """Check which essential profile fields are still missing."""
        essential_fields = {
            "age": "ton âge",
            "height_cm": "ta taille",
            "weight_kg": "ton poids",
            "goal": "ton objectif principal",
            "fitness_level": "ton niveau sportif",
            "training_frequency": "ta fréquence d'entraînement souhaitée",
        }
        important_fields = {
            "available_equipment": "le matériel dont tu disposes",
            "injuries_constraints": "d'éventuelles blessures ou contraintes",
            "dietary_preferences": "tes préférences alimentaires",
        }

        missing_essential = []
        for field, label in essential_fields.items():
            value = profile.get(field) if isinstance(profile, dict) else getattr(profile, field, None)
            if value is None:
                missing_essential.append(label)

        missing_important = []
        for field, label in important_fields.items():
            value = profile.get(field) if isinstance(profile, dict) else getattr(profile, field, None)
            if value is None:
                missing_important.append(label)

        is_complete = len(missing_essential) == 0
        all_missing = missing_essential + missing_important
        return is_complete, all_missing
