"""
Phase 02 — Goal-Aware Subtask Generation via LLM Synthesis.

Takes a ProcessedManual and a user goal prompt, then decomposes the goal
into a sequenced list of subtasks — each carrying its own VLM prompt
fragments (visual_cue + completion_criterion) for Phase 03 execution.
"""

from __future__ import annotations

import json
import logging

from google import genai

from config.settings import Settings, get_settings
from models.machine_knowledge import (
    Priority,
    PrioritizedSubtaskChecklist,
    ProcessedManual,
    Subtask,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a machine maintenance planning assistant. Given:
1. A machine's parsed manual (sections with procedures and safety info)
2. A user goal describing the maintenance task they want to perform

Your job is to produce a prioritized, sequenced subtask checklist. Each subtask must include:
- A clear, actionable instruction
- A **visual_cue**: a description of what the camera should look for to locate the relevant component \
(this will be sent to a Vision Language Model as a detection prompt)
- A **completion_criterion**: a description of what "done" looks like for this step \
(this will be sent to a VLM as a verification prompt)
- Safety prerequisites: which prior steps must be confirmed complete before this step can begin
- Priority: critical / high / routine
- Any warnings and required tools from the manual

Sequence subtasks respecting:
- Safety constraints (e.g. power down before disassembly)
- Physical access order (e.g. remove cover before accessing internals)
- Procedural dependencies (e.g. drain fluid before removing component)

Start with a safety preamble summarizing key precautions.

Respond with valid JSON matching this exact schema:
{
  "safety_preamble": "string — key safety precautions before starting",
  "estimated_complexity": "simple | moderate | complex",
  "subtasks": [
    {
      "step_number": 1,
      "title": "short title",
      "instruction": "detailed step-by-step instruction",
      "priority": "critical | high | routine",
      "visual_cue": "what the camera should look for to find the component",
      "completion_criterion": "what the camera should verify when the step is done",
      "related_section": "manual section title this step comes from",
      "warnings": ["warning1"],
      "tools_required": ["tool1"],
      "expected_outcome": "what should be true after this step",
      "safety_prerequisites": [0]
    }
  ]
}
"""


def _build_user_prompt(manual: ProcessedManual, goal: str) -> str:
    """Build the user message with manual context and goal."""
    parts: list[str] = []

    parts.append(f"# Machine: {manual.machine_id}")
    parts.append(f"# Goal: {goal}")

    # Include relevant manual sections — prioritize maintenance, safety, troubleshooting
    parts.append("\n## Manual Sections")
    priority_types = ("safety", "maintenance", "troubleshooting", "operation", "overview")
    sorted_sections = sorted(
        manual.sections,
        key=lambda s: priority_types.index(s.section_type) if s.section_type in priority_types else 99,
    )

    for section in sorted_sections:
        label = f"[{section.section_type}]" if section.section_type else ""
        parts.append(f"\n### {section.title} {label} (pp. {section.page_start}-{section.page_end})")
        content = section.content[:2000] if section.content else "(no content)"
        parts.append(content)
        if section.procedures:
            parts.append("\nProcedure steps:")
            for step in section.procedures:
                warnings = f" WARNING: {', '.join(step.warnings)}" if step.warnings else ""
                tools = f" Tools: {', '.join(step.tools_required)}" if step.tools_required else ""
                parts.append(
                    f"  {step.step_number}. {step.instruction}{warnings}{tools}"
                )

    parts.append(
        f"\nDecompose the goal \"{goal}\" into a prioritized subtask checklist as JSON. "
        "Each subtask must have a visual_cue and completion_criterion suitable for a VLM."
    )
    return "\n".join(parts)


def generate_subtasks(
    manual: ProcessedManual,
    goal: str,
    settings: Settings | None = None,
) -> PrioritizedSubtaskChecklist:
    """
    Phase 02 entry point.

    Uses Gemini to decompose a maintenance goal into a sequenced subtask
    checklist, with VLM prompt fragments for each step.

    Args:
        manual: ProcessedManual from Phase 01
        goal: User's maintenance goal (e.g. "change the oil and oil filter")
        settings: Configuration (defaults to env-based settings)

    Returns:
        PrioritizedSubtaskChecklist with VLM-ready subtasks
    """
    settings = settings or get_settings()

    logger.info("Phase 02: Generating subtasks for goal '%s' on %s", goal, manual.machine_id)
    logger.info("  Manual sections available: %d", len(manual.sections))

    client = genai.Client(api_key=settings.gemini_api_key)
    user_prompt = _build_user_prompt(manual, goal)

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=user_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=4096,
            response_mime_type="application/json",
        ),
    )

    response_text = response.text
    # response_mime_type should give clean JSON, but handle fences just in case
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    try:
        data = json.loads(response_text.strip())
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        logger.debug("Raw response: %s", response_text)
        return PrioritizedSubtaskChecklist(
            machine_id=manual.machine_id,
            goal=goal,
            safety_preamble="Error: Could not generate maintenance plan. Please review manually.",
        )

    subtasks = []
    for item in data.get("subtasks", []):
        subtasks.append(
            Subtask(
                step_number=item.get("step_number", 0),
                title=item.get("title", ""),
                instruction=item.get("instruction", ""),
                priority=Priority(item.get("priority", "routine")),
                visual_cue=item.get("visual_cue", ""),
                completion_criterion=item.get("completion_criterion", ""),
                related_section=item.get("related_section", ""),
                warnings=item.get("warnings", []),
                tools_required=item.get("tools_required", []),
                expected_outcome=item.get("expected_outcome", ""),
                safety_prerequisites=item.get("safety_prerequisites", []),
            )
        )

    checklist = PrioritizedSubtaskChecklist(
        machine_id=manual.machine_id,
        goal=goal,
        subtasks=subtasks,
        safety_preamble=data.get("safety_preamble", ""),
        estimated_complexity=data.get("estimated_complexity", ""),
    )

    logger.info(
        "Phase 02 complete: %d subtasks generated (%s complexity)",
        len(subtasks),
        checklist.estimated_complexity,
    )
    return checklist
