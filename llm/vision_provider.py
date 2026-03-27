"""Vision provider for meal photo analysis using Google Gemini API."""

import base64
import httpx
import structlog

from config.settings import get_settings

logger = structlog.get_logger()

MEAL_ANALYSIS_PROMPT = (
    "Tu es un expert en nutrition. Analyse cette photo de repas et donne :\n\n"
    "1. **Identification** : Liste chaque aliment visible dans l'assiette\n"
    "2. **Quantités estimées** : Estime les quantités en grammes pour chaque aliment\n"
    "3. **Calories** : Calories estimées par aliment + total du repas\n"
    "4. **Macronutriments** :\n"
    "   - Protéines (g)\n"
    "   - Glucides (g)\n"
    "   - Lipides (g)\n"
    "   - Fibres (g)\n"
    "5. **Verdict** : Note ce repas sur 10 pour un objectif fitness "
    "(équilibre, qualité des protéines, densité nutritionnelle)\n"
    "6. **Suggestions** : Ce qui pourrait améliorer ce repas\n\n"
    "Réponds en français. Sois précis mais concis. "
    "Utilise des emojis pour rendre la réponse agréable à lire."
)


async def analyze_image_gemini(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Send an image to Google Gemini API and get a meal analysis.

    Args:
        image_bytes: Raw image bytes.
        mime_type: MIME type of the image (image/jpeg, image/png, etc.).

    Returns:
        The text analysis from Gemini.
    """
    settings = get_settings().vision
    if not settings.api_key:
        return (
            "⚠️ La fonctionnalité de scan de repas n'est pas configurée.\n"
            "Ajoute `VISION_API_KEY=ta-clé-gemini` dans le fichier `.env`."
        )

    # Encode image to base64
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    # Build Gemini API request
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.model}:generateContent?key={settings.api_key}"
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": MEAL_ANALYSIS_PROMPT},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_image,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        logger.info("Calling Gemini Vision API", model=settings.model)
        resp = await client.post(url, json=payload)

        if resp.status_code != 200:
            logger.error(
                "Gemini API error",
                status=resp.status_code,
                body=resp.text[:500],
            )
            return (
                "❌ Erreur lors de l'analyse de la photo.\n"
                f"Code : {resp.status_code}. Réessaie dans quelques instants."
            )

        data = resp.json()

        # Extract text from Gemini response
        try:
            candidates = data["candidates"]
            text = candidates[0]["content"]["parts"][0]["text"]
            return text
        except (KeyError, IndexError) as e:
            logger.error("Unexpected Gemini response format", error=str(e), data=data)
            return "❌ Réponse inattendue de l'API Vision. Réessaie."

