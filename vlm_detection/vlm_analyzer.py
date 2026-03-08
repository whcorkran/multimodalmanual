"""
Phase 03 — Goal-Aware Detection + Guided Execution via Overshoot VLM.

Uses a SINGLE CameraSource stream from the system camera. The stream runs
continuously — for each subtask the prompt is swapped between detection and
verification via stream.update_prompt(). Results are emitted through an
async callback so the web UI can render them in real time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

import overshoot

from config.settings import Settings, get_settings
from models.machine_knowledge import (
    CompletionVerdict,
    DetectionResult,
    PrioritizedSubtaskChecklist,
    SessionLog,
    Subtask,
    SubtaskLog,
)

logger = logging.getLogger(__name__)

# --- Structured output schemas for Overshoot ---

UNIFIED_SCHEMA = {
    "type": "object",
    "properties": {
        "mode": {
            "type": "string",
            "enum": ["detection", "verification"],
            "description": "Which task this response answers",
        },
        "confidence": {
            "type": "number",
            "description": "How confident you are in your assessment, 0.0 to 1.0",
        },
        "status": {
            "type": "string",
            "enum": ["ready", "unclear", "problem"],
            "description": "Detection only: ready=component visible and accessible, unclear=not sure, problem=issue seen",
        },
        "components": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Detection only: short names of components visible in the frame",
        },
        "complete": {
            "type": "boolean",
            "description": "Verification only: true if the completion criterion is visually satisfied in the current frame, false otherwise",
        },
        "observation": {
            "type": "string",
            "description": "Verification only: one sentence describing what you see that supports your complete judgment",
        },
    },
    "required": ["mode", "confidence"],
}


def _build_detection_prompt(subtask: Subtask) -> str:
    return (
        f"You are a maintenance assistant analyzing a live camera feed.\n"
        f"Current task: {subtask.title}\n"
        f"Look for: {subtask.visual_cue}\n\n"
        f"Identify the relevant components visible in this frame. "
        f"Set status to 'ready' if the component is visible and accessible, "
        f"'unclear' if you cannot confirm, or 'problem' if something looks wrong.\n\n"
        f"Respond with JSON: mode=\"detection\", components=[names], confidence=0-1, status=ready/unclear/problem."
    )


def _build_verification_prompt(subtask: Subtask) -> str:
    return (
        f"You are verifying whether a maintenance step has been completed.\n"
        f"Step performed: {subtask.instruction}\n"
        f"Completion criterion: {subtask.completion_criterion}\n\n"
        f"Look at the current frame carefully. "
        f"If you can see evidence that the criterion is satisfied, set complete=true. "
        f"If the criterion is NOT satisfied or you cannot confirm it, set complete=false.\n\n"
        f"Respond with JSON: mode=\"verification\", complete=true/false, confidence=0-1, "
        f"observation=\"one sentence about what you see\"."
    )


def _parse_result(result) -> dict | None:
    """Extract parsed JSON from an Overshoot inference result."""
    if not result or not result.ok:
        return None
    try:
        return result.result_json()
    except Exception:
        try:
            return json.loads(result.result)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Unparseable VLM result: %s", result.result)
            return None


async def _wait_for_result(
    result_holder: dict,
    error_holder: dict,
    done_event: asyncio.Event,
    timeout: int,
    expected_mode: str | None = None,
) -> dict | None:
    """Wait for a single inference result from the shared stream.

    If *expected_mode* is set (``"detection"`` or ``"verification"``),
    discard results whose ``mode`` field doesn't match — they are stale
    responses from a previous prompt.  Retries up to 3 times before
    giving up.
    """
    max_attempts = 3 if expected_mode else 1

    for _ in range(max_attempts):
        done_event.clear()
        result_holder.clear()
        error_holder.clear()

        try:
            await asyncio.wait_for(done_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("VLM inference timed out")
            return None

        if "error" in error_holder:
            logger.error("VLM error: %s", error_holder["error"])
            return None

        parsed = _parse_result(result_holder.get("data"))

        if parsed is not None and expected_mode and parsed.get("mode") != expected_mode:
            logger.debug(
                "Discarding stale result (expected mode=%s, got mode=%s)",
                expected_mode,
                parsed.get("mode"),
            )
            continue

        return parsed

    logger.warning(
        "No matching result after %d attempts (expected mode=%s)",
        max_attempts,
        expected_mode,
    )
    return None


def _parse_detection(subtask: Subtask, parsed: dict | None) -> DetectionResult:
    if parsed is None:
        return DetectionResult(
            subtask_step=subtask.step_number,
            status="unclear",
            confidence=0.0,
        )
    return DetectionResult(
        subtask_step=subtask.step_number,
        components_found=parsed.get("components", []),
        component_descriptions=[],
        confidence=float(parsed.get("confidence", 0.0)),
        status=parsed.get("status", "unclear"),
    )


def _parse_verification(subtask: Subtask, parsed: dict | None) -> CompletionVerdict:
    if parsed is None:
        return CompletionVerdict(
            subtask_step=subtask.step_number,
            complete=False,
            confidence=0.0,
            reason="VLM inference failed or timed out",
        )
    return CompletionVerdict(
        subtask_step=subtask.step_number,
        complete=bool(parsed.get("complete", False)),
        confidence=float(parsed.get("confidence", 0.0)),
        reason=parsed.get("observation", ""),
    )


RETRY_COOLDOWN_SECONDS = 5


async def run_live_detection(
    checklist: PrioritizedSubtaskChecklist,
    settings: Settings | None = None,
) -> AsyncIterator[dict]:
    """
    Phase 03 entry point — live camera streaming.

    Opens a SINGLE CameraSource stream and continuously cycles through
    subtasks. For each subtask, runs a detect → verify loop that repeats
    with a cooldown until the step is verified complete. The stream stays
    open until all subtasks are done.

    Yields SSE-ready dicts for each detection and verification result so
    the web UI can update in real time.
    """
    settings = settings or get_settings()

    if not checklist.subtasks:
        yield {"type": "session_done", "summary": "No subtasks to process."}
        return

    logger.info(
        "Phase 03: Starting live camera detection for %d subtasks on %s",
        len(checklist.subtasks),
        checklist.machine_id,
    )

    # Shared callback state
    result_holder: dict = {}
    error_holder: dict = {}
    done_event = asyncio.Event()

    def on_result(r):
        result_holder["data"] = r
        done_event.set()

    def on_error(e):
        error_holder["error"] = e
        done_event.set()

    client = overshoot.Overshoot(api_key=settings.overshoot_api_key)
    source = overshoot.CameraSource()

    initial_prompt = _build_detection_prompt(checklist.subtasks[0])

    stream = await client.streams.create(
        source=source,
        prompt=initial_prompt,
        model=settings.overshoot_model,
        on_result=on_result,
        on_error=on_error,
        output_schema=UNIFIED_SCHEMA,
        max_output_tokens=256,
        interval_seconds=2.0,
        mode="frame",
    )

    completed_steps: list[SubtaskLog] = []
    skipped_steps: list[int] = []

    try:
        completed_step_numbers: set[int] = set()

        for subtask in checklist.subtasks:
            # Check safety prerequisites
            unmet = [
                p
                for p in subtask.safety_prerequisites
                if p not in completed_step_numbers
            ]
            if unmet:
                logger.warning(
                    "  Skipping step %d — prerequisites not met: %s",
                    subtask.step_number,
                    unmet,
                )
                skipped_steps.append(subtask.step_number)
                yield {
                    "type": "step_skip",
                    "step": subtask.step_number,
                    "title": subtask.title,
                    "reason": f"Prerequisites not met: steps {unmet}",
                }
                continue

            # --- Continuous detect → verify loop until complete ---
            attempt = 0
            detection = None
            verdict = None

            while True:
                attempt += 1

                # Detection pass
                logger.info(
                    "  Detecting step %d (round %d): %s",
                    subtask.step_number,
                    attempt,
                    subtask.title,
                )
                await stream.update_prompt(_build_detection_prompt(subtask))

                parsed = await _wait_for_result(
                    result_holder,
                    error_holder,
                    done_event,
                    settings.overshoot_inference_timeout,
                    expected_mode="detection",
                )
                logger.info("    Raw detection JSON: %s", parsed)
                detection = _parse_detection(subtask, parsed)

                logger.info(
                    "    Detection: %s (confidence: %.0f%%)",
                    detection.status,
                    detection.confidence * 100,
                )
                yield {
                    "type": "detection",
                    "step": subtask.step_number,
                    "title": subtask.title,
                    "status": detection.status,
                    "components_found": detection.components_found,
                    "component_descriptions": detection.component_descriptions,
                    "confidence": detection.confidence,
                    "attempt": attempt,
                }

                # Verification pass
                logger.info(
                    "  Verifying step %d (round %d)", subtask.step_number, attempt
                )
                await stream.update_prompt(_build_verification_prompt(subtask))

                parsed = await _wait_for_result(
                    result_holder,
                    error_holder,
                    done_event,
                    settings.overshoot_inference_timeout,
                    expected_mode="verification",
                )
                logger.info("    Raw verification JSON: %s", parsed)
                verdict = _parse_verification(subtask, parsed)

                logger.info(
                    "    Verification: complete=%s (confidence: %.0f%%) — %s",
                    verdict.complete,
                    verdict.confidence * 100,
                    verdict.reason,
                )
                yield {
                    "type": "verification",
                    "step": subtask.step_number,
                    "title": subtask.title,
                    "attempt": attempt,
                    "complete": verdict.complete,
                    "confidence": verdict.confidence,
                    "reason": verdict.reason,
                }

                if verdict.complete:
                    break

                # Not complete — wait and try again
                logger.info(
                    "    Step %d not complete, waiting %ds before re-checking...",
                    subtask.step_number,
                    RETRY_COOLDOWN_SECONDS,
                )
                yield {
                    "type": "waiting",
                    "step": subtask.step_number,
                    "title": subtask.title,
                    "seconds": RETRY_COOLDOWN_SECONDS,
                    "attempt": attempt,
                }
                await asyncio.sleep(RETRY_COOLDOWN_SECONDS)

            completed_steps.append(
                SubtaskLog(
                    subtask_step=subtask.step_number,
                    title=subtask.title,
                    detection=detection,
                    verdict=verdict,
                    attempts=attempt,
                )
            )

            completed_step_numbers.add(subtask.step_number)
            yield {
                "type": "step_complete",
                "step": subtask.step_number,
                "title": subtask.title,
                "attempts": attempt,
            }

    finally:
        await stream.close()
        await client.close()

    done_count = sum(1 for s in completed_steps if s.verdict and s.verdict.complete)
    total = len(checklist.subtasks)
    summary = (
        f"Processed {len(completed_steps)}/{total} subtasks. "
        f"{done_count} verified complete, {len(skipped_steps)} skipped."
    )

    logger.info("Phase 03 complete: %s", summary)

    yield {
        "type": "session_done",
        "summary": summary,
        "completed": [
            {
                "step": s.subtask_step,
                "title": s.title,
                "detection_status": s.detection.status if s.detection else "n/a",
                "complete": s.verdict.complete if s.verdict else False,
                "confidence": s.verdict.confidence if s.verdict else 0,
                "attempts": s.attempts,
            }
            for s in completed_steps
        ],
        "skipped": skipped_steps,
    }
