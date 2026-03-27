"""CLI interface for testing the fitness coach without Telegram."""

import asyncio
import structlog

from coaching.engine import CoachingEngine
from database.database import get_session, init_db, close_db
from database.repositories import UserRepository
from llm.ollama_provider import create_llm_provider
from config.settings import get_settings

logger = structlog.get_logger()

CLI_USER_ID = "cli_user_1"


async def run_cli():
    """Run the fitness coach in CLI mode."""
    settings = get_settings()
    llm = create_llm_provider(settings.llm)
    engine = CoachingEngine(llm)

    await init_db()

    print("=" * 60)
    print("🏋️ Coach Fitness IA — Mode CLI")
    print("=" * 60)
    print("Tape ton message et appuie sur Entrée.")
    print("Commandes spéciales :")
    print("  /quit      — Quitter")
    print("  /morning   — Simuler le message du matin")
    print("  /evening   — Simuler le check-in du soir")
    print("  /profile   — Voir ton profil")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("Toi > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nÀ bientôt ! 💪")
            break

        if not user_input:
            continue

        if user_input.lower() == "/quit":
            print("À bientôt ! Continue à t'entraîner 💪")
            break

        session = await get_session()
        try:
            if user_input.lower() == "/morning":
                user_repo = UserRepository(session)
                user = await user_repo.get_or_create(CLI_USER_ID, "cli")
                reply = await engine.generate_morning_message(session, user.id)
                await session.commit()
            elif user_input.lower() == "/evening":
                user_repo = UserRepository(session)
                user = await user_repo.get_or_create(CLI_USER_ID, "cli")
                reply = await engine.generate_evening_checkin(session, user.id)
                await session.commit()
            elif user_input.lower() == "/profile":
                user_repo = UserRepository(session)
                user = await user_repo.get_by_external_id(CLI_USER_ID)
                if user and user.profile:
                    p = user.profile
                    fields = {
                        "Âge": p.age, "Taille (cm)": p.height_cm, "Poids (kg)": p.weight_kg,
                        "Sexe": p.sex, "Niveau": p.fitness_level, "Objectif": p.goal,
                        "Matériel": p.available_equipment, "Fréquence": p.training_frequency,
                        "Contraintes": p.injuries_constraints, "Alimentation": p.dietary_preferences,
                        "Allergies": p.allergies, "Budget": p.food_budget,
                        "Rythme de vie": p.lifestyle_rhythm,
                    }
                    reply = "📋 Ton profil :\n" + "\n".join(
                        f"  • {k} : {v}" for k, v in fields.items() if v is not None
                    )
                    if not any(v is not None for v in fields.values()):
                        reply = "Profil vide. Parle-moi de toi pour le compléter !"
                else:
                    reply = "Aucun profil trouvé. Envoie un message pour commencer !"
            else:
                reply = await engine.handle_message(
                    session, CLI_USER_ID, user_input, platform="cli"
                )
        finally:
            await session.close()

        print(f"\n🏋️ Coach > {reply}\n")

    await llm.close()
    await close_db()


def main():
    """Entry point for CLI mode."""
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()

