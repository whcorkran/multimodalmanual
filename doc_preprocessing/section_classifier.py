"""
Section Classifier

Splits parsed PDF pages into labeled ManualSection objects based on
heading detection and keyword matching. Identifies maintenance,
troubleshooting, safety, operation, and overview sections.
"""

from __future__ import annotations

import logging
import re

from models.machine_knowledge import ManualPage, ManualSection

logger = logging.getLogger(__name__)

# Keywords that indicate section types (checked against heading text)
_SECTION_KEYWORDS: dict[str, list[str]] = {
    "maintenance": [
        "maintenance", "servicing", "lubrication", "inspection",
        "preventive", "scheduled maintenance", "routine",
    ],
    "troubleshooting": [
        "troubleshoot", "fault", "error", "diagnostic", "alarm",
        "problem", "remedy", "corrective",
    ],
    "safety": [
        "safety", "warning", "caution", "danger", "hazard",
        "protective", "ppe", "lockout", "tagout",
    ],
    "operation": [
        "operation", "operating", "startup", "shutdown", "procedure",
        "instruction", "how to", "setup", "set-up",
    ],
    "overview": [
        "overview", "introduction", "general", "description",
        "specification", "contents", "table of contents",
    ],
}

# Pattern for lines that look like section headings:
# all-caps lines, numbered headings (1. Title, Chapter 2), or short bold-style lines
_HEADING_PATTERN = re.compile(
    r"^(?:"
    r"(?:chapter|section|part)\s*\d+[.:]\s*.+|"  # Chapter 1: Title
    r"\d{1,2}(?:\.\d{1,2})*\s+[A-Z].{2,80}|"     # 1.2 Some Heading
    r"[A-Z][A-Z\s\-&/]{4,60}"                      # ALL CAPS HEADING
    r")$",
    re.MULTILINE,
)


def classify_sections(pages: list[ManualPage]) -> list[ManualSection]:
    """
    Analyze parsed pages and split them into labeled sections.

    Detects section boundaries via heading patterns, then classifies
    each section by matching heading text against keyword lists.
    """
    headings = _detect_headings(pages)

    if not headings:
        # No headings detected — treat the entire document as one section
        logger.info("No section headings detected, treating as single section")
        full_text = "\n".join(p.text for p in pages)
        section_type = _classify_heading(full_text[:500])
        return [ManualSection(
            title="Full Document",
            section_type=section_type or "overview",
            page_start=1,
            page_end=len(pages),
            content=full_text,
        )]

    sections: list[ManualSection] = []

    for i, (heading_text, heading_page) in enumerate(headings):
        # Section runs from this heading to the next heading (or end of doc)
        if i + 1 < len(headings):
            end_page = headings[i + 1][1]
        else:
            end_page = len(pages)

        # Collect content for this section
        content_parts: list[str] = []
        for p in pages:
            if heading_page <= p.page_number <= end_page:
                content_parts.append(p.text)

        content = "\n".join(content_parts)
        section_type = _classify_heading(heading_text)

        sections.append(ManualSection(
            title=heading_text.strip(),
            section_type=section_type,
            page_start=heading_page,
            page_end=end_page,
            content=content,
        ))

    logger.info(
        "Classified %d sections: %s",
        len(sections),
        ", ".join(f"{s.title[:30]}[{s.section_type}]" for s in sections),
    )

    return sections


def _detect_headings(pages: list[ManualPage]) -> list[tuple[str, int]]:
    """
    Find section headings across all pages.

    Returns:
        List of (heading_text, page_number) tuples, ordered by appearance.
    """
    headings: list[tuple[str, int]] = []

    for page in pages:
        for match in _HEADING_PATTERN.finditer(page.text):
            heading = match.group(0).strip()
            # Skip very short matches or lines that are just numbers
            if len(heading) < 5 or heading.replace(" ", "").isdigit():
                continue
            headings.append((heading, page.page_number))

    return headings


def _classify_heading(text: str) -> str:
    """Classify a heading or text block into a section type."""
    text_lower = text.lower()
    for section_type, keywords in _SECTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return section_type
    return ""
