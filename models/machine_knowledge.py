from __future__ import annotations

from enum import Enum

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


# ---------------------------------------------------------------------------
# Phase 02 — Goal-Aware Subtask Generation models
# ---------------------------------------------------------------------------


class Priority(str, Enum):
    critical = "critical"
    high = "high"
    routine = "routine"


class Subtask(BaseModel):
    """A single maintenance subtask with VLM prompt fragments for Phase 03."""

    step_number: int
    title: str
    instruction: str
    priority: Priority = Priority.routine
    visual_cue: str = ""  # VLM detection prompt (e.g. "oil drain plug on underside")
    completion_criterion: str = ""  # VLM verification prompt (e.g. "plug reinstalled, no seepage")
    related_section: str = ""  # manual section title from Phase 01
    warnings: list[str] = Field(default_factory=list)
    tools_required: list[str] = Field(default_factory=list)
    expected_outcome: str = ""
    safety_prerequisites: list[int] = Field(default_factory=list)  # step_numbers that must complete first


class PrioritizedSubtaskChecklist(BaseModel):
    """Phase 02 output — sequenced, severity-tagged maintenance plan with VLM prompts."""

    machine_id: str
    goal: str = ""
    subtasks: list[Subtask] = Field(default_factory=list)
    safety_preamble: str = ""
    estimated_complexity: str = ""  # "simple", "moderate", "complex"


# ---------------------------------------------------------------------------
# Phase 03 — Goal-Aware Detection + Guided Execution models
# ---------------------------------------------------------------------------


class DetectionResult(BaseModel):
    """Overshoot VLM detection output for a single subtask."""

    subtask_step: int
    components_found: list[str] = Field(default_factory=list)
    component_descriptions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    status: str = ""  # "ready", "unclear", "problem"


class CompletionVerdict(BaseModel):
    """Overshoot VLM verification of whether a subtask has been completed."""

    subtask_step: int
    complete: bool = False
    confidence: float = 0.0
    reason: str = ""


class SubtaskLog(BaseModel):
    """Execution record for a single completed subtask."""

    subtask_step: int
    title: str = ""
    detection: DetectionResult | None = None
    verdict: CompletionVerdict | None = None
    attempts: int = 1


class SessionLog(BaseModel):
    """Phase 03 output — per-subtask completion log for the full session."""

    machine_id: str
    goal: str = ""
    completed: list[SubtaskLog] = Field(default_factory=list)
    skipped: list[int] = Field(default_factory=list)
    summary: str = ""
