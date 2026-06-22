"""Styled PDF generation for coaching plans and reports."""

import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


OUTPUT_DIR = Path("output/pdf")


@dataclass
class PDFSection:
    """One visual section in a generated coach PDF."""

    title: str
    body: str
    accent: str = "#0EA5A4"


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "coach-report"


def _clean_text(text: str) -> str:
    text = text.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def _paragraphs(text: str, style: ParagraphStyle) -> list:
    flowables = []
    for block in _clean_text(text).split("\n"):
        block = block.strip()
        if not block:
            flowables.append(Spacer(1, 0.12 * cm))
            continue
        flowables.append(Paragraph(block, style))
        flowables.append(Spacer(1, 0.08 * cm))
    return flowables


def _section_card(section: PDFSection, styles) -> Table:
    accent = colors.HexColor(section.accent)
    title = Paragraph(section.title, styles["SectionTitle"])
    body_parts = _paragraphs(section.body, styles["Body"])
    body_table = Table([[part] for part in body_parts], colWidths=[15.2 * cm])
    body_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    card = Table(
        [
            [title],
            [body_table],
        ],
        colWidths=[16.2 * cm],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                ("BOX", (0, 0), (-1, -1), 1.0, colors.HexColor("#CBD5E1")),
                ("LINEBEFORE", (0, 0), (0, -1), 6, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return card


def _build_styles():
    base = getSampleStyleSheet()
    base.add(
        ParagraphStyle(
            name="HeroTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.white,
            alignment=TA_CENTER,
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="HeroSubtitle",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#E0F2FE"),
            alignment=TA_CENTER,
        )
    )
    base.add(
        ParagraphStyle(
            name="SectionTitle",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=8,
        )
    )
    base.add(
        ParagraphStyle(
            name="Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1E293B"),
        )
    )
    base.add(
        ParagraphStyle(
            name="Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B"),
            alignment=TA_CENTER,
        )
    )
    return base


def create_coach_pdf(
    title: str,
    subtitle: str,
    sections: list[PDFSection],
    filename_prefix: str = "fitness-coach",
    output_dir: Path | str = OUTPUT_DIR,
) -> str:
    """Create a visually polished coaching PDF and return its file path."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    file_path = out_dir / f"{_slugify(filename_prefix)}-{timestamp}.pdf"

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        rightMargin=1.4 * cm,
        leftMargin=1.4 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=title,
        author="Fitness Coach AI",
    )

    hero = Table(
        [
            [Paragraph(_clean_text(title), styles["HeroTitle"])],
            [Paragraph(_clean_text(subtitle), styles["HeroSubtitle"])],
        ],
        colWidths=[16.8 * cm],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0F766E")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0F766E")),
                ("TOPPADDING", (0, 0), (-1, -1), 18),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 18),
                ("LEFTPADDING", (0, 0), (-1, -1), 18),
                ("RIGHTPADDING", (0, 0), (-1, -1), 18),
            ]
        )
    )

    story = [hero, Spacer(1, 0.45 * cm)]
    accent_cycle = ["#0EA5A4", "#F97316", "#2563EB", "#7C3AED", "#16A34A"]
    for index, section in enumerate(sections):
        if not section.accent:
            section.accent = accent_cycle[index % len(accent_cycle)]
        story.append(_section_card(section, styles))
        story.append(Spacer(1, 0.28 * cm))

    generated_at = datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(f"Généré le {generated_at}", styles["Small"]))

    doc.build(story)
    return os.path.abspath(file_path)


def sections_from_coach_text(text: str) -> list[PDFSection]:
    """Convert coach text into styled PDF sections."""
    clean = _clean_text(text)
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", clean) if chunk.strip()]
    if not chunks:
        return [PDFSection("Plan coach", "Aucun contenu disponible.", "#0EA5A4")]

    sections: list[PDFSection] = []
    accents = ["#0EA5A4", "#F97316", "#2563EB", "#7C3AED", "#16A34A"]
    for index, chunk in enumerate(chunks[:8]):
        lines = chunk.split("\n")
        first = lines[0].strip()
        if len(first) <= 80 and len(lines) > 1:
            title = first.strip("#:- ")
            body = "\n".join(lines[1:]).strip()
        else:
            title = "Section coach" if index else "Plan personnalisé"
            body = chunk
        sections.append(PDFSection(title=title, body=body, accent=accents[index % len(accents)]))
    return sections
