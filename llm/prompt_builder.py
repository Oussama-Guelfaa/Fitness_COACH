"""Prompt construction for the fitness coach.

Builds context-rich prompts by injecting user profile, history, and constraints
into the system prompt before every LLM call.
"""

from database.models import UserProfile, CheckIn, WorkoutLog
from llm.base import LLMMessage

SYSTEM_BASE = """Tu es un coach fitness IA bienveillant, professionnel et motivant.

RÈGLES STRICTES :
- Tu n'es PAS médecin. Tu ne poses JAMAIS de diagnostic médical.
- Si l'utilisateur mentionne une blessure grave, douleur importante, problème médical ou trouble alimentaire, tu recommandes TOUJOURS de consulter un professionnel de santé.
- Tu restes prudent dans tes recommandations si des contraintes de santé sont mentionnées.
- Tu ne prescris JAMAIS de médicaments, compléments médicaux, ou régimes extrêmes.
- Tu adaptes tes conseils au niveau, aux objectifs et aux contraintes de l'utilisateur.
- Tu réponds en français sauf si l'utilisateur s'adresse à toi dans une autre langue.
- Tu es encourageant mais réaliste.
- Tu structures tes réponses de manière claire (listes, sections).

RÈGLES NUTRITION — quand tu proposes un repas ou un plan alimentaire :
- Indique TOUJOURS les calories approximatives de chaque repas et le total journalier.
- Précise les quantités exactes (en grammes, ml, unités) pour chaque aliment.
- Estime un prix approximatif (en €) pour chaque repas et le total journalier.
- Tiens compte du budget alimentaire de l'utilisateur si renseigné.
- Exemple de format attendu :
  🍽️ Déjeuner (~650 kcal — ~4,50€)
  - 150g de blanc de poulet (grillé)
  - 200g de riz complet (cuit)
  - 100g de brocolis vapeur
  - 1 cuillère à soupe d'huile d'olive

RÈGLES EXERCICES — quand tu proposes des exercices :
- Pour chaque exercice mentionné, inclus un lien YouTube vers une vidéo démonstrative.
- Utilise le format : [Nom de l'exercice](https://www.youtube.com/results?search_query=nom+exercice+tutoriel)
- Cela permet à l'utilisateur de voir la bonne forme d'exécution.
"""

ONBOARDING_PROMPT = """L'utilisateur vient de commencer. Tu dois l'accueillir chaleureusement et lui poser des questions pour compléter son profil fitness.

Voici les informations qu'il te faut (pose-les progressivement, pas tout d'un coup) :
- Âge, taille, poids, sexe
- Niveau sportif (débutant, intermédiaire, avancé)
- Objectif (perte de poids, prise de masse, recomposition, remise en forme, etc.)
- Matériel disponible (salle de sport, haltères maison, poids du corps uniquement, etc.)
- Fréquence d'entraînement souhaitée
- Contraintes physiques ou blessures
- Préférences alimentaires, allergies, budget alimentaire
- Rythme de vie (sédentaire, actif, horaires de travail)
- Toute autre info utile

Commence par te présenter et poser les premières questions de manière naturelle et engageante.
"""


def _value(item, field: str, default=None):
    """Read a field from either a SQLAlchemy object or serialized state dict."""
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _format_date(value) -> str:
    if value is None:
        return "?"
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m")
    return str(value)[:10]


def _format_profile(profile: UserProfile | dict | None) -> str:
    """Format user profile as context string."""
    if profile is None:
        return "Profil : aucune information disponible."

    parts = ["=== PROFIL UTILISATEUR ==="]
    field_labels = {
        "age": "Âge", "height_cm": "Taille (cm)", "weight_kg": "Poids (kg)",
        "sex": "Sexe", "fitness_level": "Niveau sportif", "goal": "Objectif",
        "available_equipment": "Matériel disponible",
        "training_frequency": "Fréquence d'entraînement",
        "injuries_constraints": "Contraintes / Blessures",
        "dietary_preferences": "Préférences alimentaires",
        "allergies": "Allergies", "food_budget": "Budget alimentaire",
        "lifestyle_rhythm": "Rythme de vie",
        "wake_up_time": "Heure de réveil", "sleep_time": "Heure de coucher",
        "extra_info": "Informations supplémentaires",
    }
    for field, label in field_labels.items():
        value = _value(profile, field)
        if value is not None:
            parts.append(f"- {label} : {value}")

    if not any(_value(profile, f) for f in field_labels):
        parts.append("Profil non encore renseigné.")

    return "\n".join(parts)


def _format_checkins(checkins: list[CheckIn | dict]) -> str:
    """Format recent check-ins for context."""
    if not checkins:
        return ""
    parts = ["=== CHECK-INS RÉCENTS ==="]
    for ci in checkins[-5:]:
        date_str = _format_date(_value(ci, "date"))
        line = f"- {date_str} ({_value(ci, 'check_in_type')})"
        if _value(ci, "energy_level"):
            line += f" | Énergie: {_value(ci, 'energy_level')}/10"
        if _value(ci, "motivation_level"):
            line += f" | Motivation: {_value(ci, 'motivation_level')}/10"
        if _value(ci, "mood"):
            line += f" | Humeur: {_value(ci, 'mood')}"
        if _value(ci, "pain_reported"):
            line += f" | Douleur: {_value(ci, 'pain_reported')}"
        if _value(ci, "notes"):
            line += f" | Notes: {_value(ci, 'notes')}"
        parts.append(line)
    return "\n".join(parts)


def _format_workouts(workouts: list[WorkoutLog | dict]) -> str:
    """Format recent workout logs for context."""
    if not workouts:
        return ""
    parts = ["=== SÉANCES RÉCENTES ==="]
    for w in workouts[-5:]:
        date_str = _format_date(_value(w, "date"))
        status = "✅ Faite" if _value(w, "completed") else "❌ Non faite"
        line = f"- {date_str} : {status}"
        if _value(w, "actual_workout"):
            line += f" | {_value(w, 'actual_workout')[:80]}"
        if _value(w, "difficulty_rating"):
            line += f" | Difficulté: {_value(w, 'difficulty_rating')}/10"
        parts.append(line)
    return "\n".join(parts)


def build_system_prompt(
    profile: UserProfile | dict | None = None,
    checkins: list[CheckIn | dict] | None = None,
    workouts: list[WorkoutLog | dict] | None = None,
    is_onboarding: bool = False,
    extra_instructions: str = "",
) -> LLMMessage:
    """Build a rich system prompt with all available context."""
    parts = [SYSTEM_BASE]

    if is_onboarding:
        parts.append(ONBOARDING_PROMPT)

    parts.append(_format_profile(profile))

    if checkins:
        parts.append(_format_checkins(checkins))
    if workouts:
        parts.append(_format_workouts(workouts))
    if extra_instructions:
        parts.append(f"\n=== INSTRUCTIONS SUPPLÉMENTAIRES ===\n{extra_instructions}")

    return LLMMessage(role="system", content="\n\n".join(parts))
