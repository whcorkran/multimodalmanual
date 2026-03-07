from __future__ import annotations

from pydantic import BaseModel, Field


class ManualSource(BaseModel):
    """Where the manual PDF came from."""

    origin: str  # "upload" or "web_search"
    url: str = ""
    local_path: str = ""
    title: str = ""


class ProcedureStep(BaseModel):
    """A single step within a maintenance/operating procedure."""

    step_number: int
    instruction: str
    warnings: list[str] = Field(default_factory=list)
    tools_required: list[str] = Field(default_factory=list)
    expected_outcome: str = ""


class ManualSection(BaseModel):
    """A labeled section extracted from the manual."""

    title: str
    section_type: str = ""  # "maintenance", "troubleshooting", "safety", "operation", "overview"
    page_start: int = 0
    page_end: int = 0
    content: str = ""
    procedures: list[ProcedureStep] = Field(default_factory=list)


class ManualPage(BaseModel):
    """A single page from the PDF with text and image references."""

    page_number: int
    text: str = ""
    image_paths: list[str] = Field(default_factory=list)


class ProcessedManual(BaseModel):
    """
    The unified output of manual acquisition + preprocessing.

    Contains the full parsed content of a machine's operating manual,
    structured for downstream use by the VLM and subtask generator.
    """

    machine_id: str
    source: ManualSource
    pages: list[ManualPage] = Field(default_factory=list)
    sections: list[ManualSection] = Field(default_factory=list)
    full_text: str = ""
