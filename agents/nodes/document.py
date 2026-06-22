"""Document generation node for automatic PDF requests."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from database.repositories import DocumentRepository
from services.pdf_report import create_coach_pdf, sections_from_coach_text


async def document_generator(state: CoachState, session: AsyncSession) -> dict:
    """Generate a styled PDF when the router detected a document request."""
    request = state.get("document_request") or {}
    if state.get("intent") != "document_request" or not request:
        return {}

    title = request.get("title") or "Document Coach Fitness"
    subtitle = request.get("subtitle") or "Plan personnalisé généré par le coach"
    document_type = request.get("document_type") or "coach_report"
    filename_prefix = request.get("filename_prefix") or "document-coach"

    file_path = create_coach_pdf(
        title=title,
        subtitle=subtitle,
        sections=sections_from_coach_text(state.get("candidate_response") or state.get("final_response", "")),
        filename_prefix=f"{state.get('external_id', 'user')}-{filename_prefix}",
    )
    document = await DocumentRepository(session).create_document(
        user_id=state["user_id"],
        document_type=document_type,
        title=title,
        file_path=file_path,
        source_run_id=state.get("run_id"),
        metadata={"request": request, "intent": state.get("intent")},
    )

    final_response = state.get("final_response", "").strip()
    if state.get("platform") == "telegram":
        document_note = "PDF généré. Je te l'envoie en pièce jointe."
    else:
        document_note = f"PDF généré : {file_path}"
    if final_response:
        final_response = (
            f"{final_response}\n\n"
            f"{document_note}"
        )
    else:
        final_response = document_note

    await record_event(
        session,
        state,
        "document_generator",
        "pdf_generated",
        {
            "document_id": document.id,
            "document_type": document_type,
            "file_path": file_path,
        },
    )
    return {
        "final_response": final_response,
        "generated_document_path": file_path,
        "generated_document_id": document.id,
        "generated_document_title": title,
    }
