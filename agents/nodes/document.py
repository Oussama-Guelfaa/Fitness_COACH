"""Document generation node for automatic PDF requests."""

from sqlalchemy.ext.asyncio import AsyncSession

from agents.nodes.events import record_event
from agents.state import CoachState
from database.repositories import DocumentRepository
from services.pdf_report import PDFSection, create_coach_pdf, sections_from_coach_text


async def document_generator(state: CoachState, session: AsyncSession) -> dict:
    """Generate a styled PDF when the router detected a document request."""
    request = state.get("document_request") or {}
    if state.get("intent") != "document_request" or not request:
        return {}

    title = request.get("title") or "Document Coach Fitness"
    subtitle = request.get("subtitle") or "Plan personnalisé généré par le coach"
    document_type = request.get("document_type") or "coach_report"
    filename_prefix = request.get("filename_prefix") or "document-coach"
    document_content = (state.get("candidate_response") or state.get("final_response", "")).strip()
    user_request = state.get("incoming_message", "").strip()

    sections = []
    if user_request:
        sections.append(
            PDFSection(
                "Demande utilisateur",
                user_request,
                "#2563EB",
            )
        )
    sections.extend(sections_from_coach_text(document_content))

    file_path = create_coach_pdf(
        title=title,
        subtitle=subtitle,
        sections=sections,
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

    if state.get("platform") == "telegram":
        document_note = "J'ai généré le PDF adapté à ta demande. Je te l'envoie en pièce jointe."
    else:
        document_note = f"PDF généré avec le contenu adapté à ta demande : {file_path}"
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
            "content_length": len(document_content),
        },
    )
    return {
        "final_response": final_response,
        "generated_document_path": file_path,
        "generated_document_id": document.id,
        "generated_document_title": title,
    }
