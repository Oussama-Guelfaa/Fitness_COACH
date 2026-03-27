"""Safety guardrails — detect sensitive situations and add appropriate warnings."""

import re

# Keywords that trigger safety checks
INJURY_KEYWORDS = [
    "blessure", "blessé", "fracture", "entorse", "luxation", "déchirure",
    "tendinite", "hernie", "opération", "chirurgie", "plâtre", "béquilles",
]

PAIN_KEYWORDS = [
    "douleur", "mal à", "j'ai mal", "ça fait mal", "souffre", "souffrance",
    "douloureux", "inflammation", "gonflé", "enflé",
]

MEDICAL_KEYWORDS = [
    "médecin", "docteur", "hôpital", "urgence", "diabète", "cardiaque",
    "hypertension", "asthme", "épilepsie", "enceinte", "grossesse",
    "médicament", "traitement médical", "problème de santé",
]

EATING_DISORDER_KEYWORDS = [
    "anorexie", "boulimie", "trouble alimentaire", "ne mange plus",
    "je ne mange pas", "purge", "vomir", "vomissement", "obsession",
    "trop maigre", "trop gros", "je me déteste",
]

SAFETY_WARNING = (
    "⚠️ **Attention** : Ce que tu décris semble nécessiter l'avis d'un professionnel de santé. "
    "Je ne suis qu'un coach IA et je ne peux pas remplacer un médecin, kinésithérapeute ou "
    "diététicien. Je te recommande fortement de consulter un professionnel avant de poursuivre."
)


def detect_safety_concerns(text: str) -> dict:
    """Analyze text for safety-related keywords and return detected concerns."""
    text_lower = text.lower()
    concerns = {
        "injury": False,
        "pain": False,
        "medical": False,
        "eating_disorder": False,
    }

    for kw in INJURY_KEYWORDS:
        if kw in text_lower:
            concerns["injury"] = True
            break

    for kw in PAIN_KEYWORDS:
        if kw in text_lower:
            concerns["pain"] = True
            break

    for kw in MEDICAL_KEYWORDS:
        if kw in text_lower:
            concerns["medical"] = True
            break

    for kw in EATING_DISORDER_KEYWORDS:
        if kw in text_lower:
            concerns["eating_disorder"] = True
            break

    return concerns


def has_safety_concern(text: str) -> bool:
    """Check if any safety concern is detected."""
    concerns = detect_safety_concerns(text)
    return any(concerns.values())


def get_safety_instructions(text: str) -> str:
    """Generate extra instructions for the LLM based on detected safety concerns."""
    concerns = detect_safety_concerns(text)
    if not any(concerns.values()):
        return ""

    instructions = [
        "ALERTE SÉCURITÉ — L'utilisateur a mentionné un sujet sensible.",
        "Tu DOIS :",
        "1. Reconnaître ce que l'utilisateur a dit avec empathie.",
        "2. Rappeler que tu n'es PAS médecin.",
        "3. Recommander de consulter un professionnel de santé adapté.",
        "4. Ne PAS donner de conseil médical ou de diagnostic.",
    ]

    if concerns["injury"]:
        instructions.append("5. Ne PAS proposer d'exercices qui pourraient aggraver la blessure.")
    if concerns["pain"]:
        instructions.append("5. Suggérer de ne pas forcer tant que la douleur persiste.")
    if concerns["eating_disorder"]:
        instructions.append("5. Être particulièrement délicat et orienter vers un spécialiste TCA.")
        instructions.append("6. Ne PAS parler de restriction calorique ou de perte de poids.")
    if concerns["medical"]:
        instructions.append("5. Adapter les recommandations en tenant compte de la condition médicale.")

    return "\n".join(instructions)

