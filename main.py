"""
Machine Maintenance Assistant — Pipeline Orchestrator

Acquires a machine manual, generates goal-aware subtasks, and runs
VLM-powered detection + verification on machine video.

Usage:
    # Phase 01 only (manual acquisition):
    uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --phase 1

    # Phases 01-02 (manual + subtask generation):
    uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil"

    # Full pipeline (Phases 01-03) with live camera detection:
    uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil"

    # Launch web UI (Phase 04):
    uv run python main.py --serve
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from dotenv import load_dotenv

from phase01_intelligence.pipeline import process_manual, save_processed_manual


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Machine Maintenance Assistant — acquire, analyze, and plan maintenance",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Launch the web UI (Phase 04) instead of running the CLI pipeline",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the web UI (default: 8000)",
    )
    parser.add_argument(
        "machine_id",
        nargs="?",
        default=None,
        help="Machine name, model number, or serial (e.g. 'Haas VF-2 CNC Mill')",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help="Path to a local PDF manual (skips web search)",
    )
    parser.add_argument(
        "--goal",
        default=None,
        help="Maintenance goal (e.g. 'change the oil and oil filter'). Required for Phase 02+.",
    )
    parser.add_argument(
        "--phase",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="Run pipeline up to this phase (default: 3)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="processed_manual.json",
        help="Output path for the processed manual JSON (default: processed_manual.json)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # --- Phase 04: Web UI ---
    if args.serve:
        import uvicorn
        print(f"Starting web UI on http://localhost:{args.port}")
        uvicorn.run("viz_io.app:app", host="0.0.0.0", port=args.port, reload=False)
        return

    if not args.machine_id:
        parser.error("machine_id is required (or use --serve for the web UI)")

    # --- Phase 01: Manual Acquisition & Preprocessing ---
    manual = process_manual(args.machine_id, pdf_path=args.pdf)

    print(f"\n{'=' * 60}")
    print(f"Machine: {manual.machine_id}")
    print(f"Source: {manual.source.origin}", end="")
    if manual.source.url:
        print(f" ({manual.source.url})")
    elif manual.source.local_path:
        print(f" ({manual.source.local_path})")
    else:
        print()
    print(f"Pages: {len(manual.pages)}")
    print(f"Images extracted: {sum(len(p.image_paths) for p in manual.pages)}")
    print(f"Sections: {len(manual.sections)}")
    for section in manual.sections:
        label = f"[{section.section_type}]" if section.section_type else ""
        print(f"  - {section.title[:50]} {label} (pp. {section.page_start}-{section.page_end})")
    print(f"{'=' * 60}\n")

    save_processed_manual(manual, args.output)
    print(f"Processed manual saved to: {args.output}")

    if args.phase < 2:
        return

    # --- Phase 02: Goal-Aware Subtask Generation ---
    if not args.goal:
        print("\nPhase 02 requires --goal. Example: --goal 'change the oil and oil filter'")
        return

    from subtask_generation.synthesizer import generate_subtasks

    print(f"\n{'=' * 60}")
    print(f"Phase 02: Subtask Generation — \"{args.goal}\"")
    print(f"{'=' * 60}")

    checklist = generate_subtasks(manual, goal=args.goal)

    if checklist.safety_preamble:
        print(f"\nSAFETY: {checklist.safety_preamble}")
    print(f"Complexity: {checklist.estimated_complexity}")
    print(f"Subtasks: {len(checklist.subtasks)}\n")
    for task in checklist.subtasks:
        priority_icon = {"critical": "[!!!]", "high": "[!! ]", "routine": "[   ]"}
        print(
            f"  {priority_icon.get(task.priority.value, '[?  ]')} "
            f"Step {task.step_number}: {task.title}"
        )
        print(f"        {task.instruction[:100]}")
        if task.visual_cue:
            print(f"        Eye: {task.visual_cue[:80]}")
        if task.completion_criterion:
            print(f"        Done: {task.completion_criterion[:80]}")
        if task.warnings:
            for w in task.warnings:
                print(f"        WARNING: {w}")
        if task.tools_required:
            print(f"        Tools: {', '.join(task.tools_required)}")
        print()

    checklist_path = args.output.replace(".json", "_checklist.json")
    with open(checklist_path, "w") as f:
        json.dump(checklist.model_dump(), f, indent=2)
    print(f"Subtask checklist saved to: {checklist_path}")

    if args.phase < 3:
        return

    # --- Phase 03: Live Camera Detection + Verification ---
    from vlm_detection.vlm_analyzer import run_live_detection

    print(f"\n{'=' * 60}")
    print("Phase 03: Live Camera Detection + Verification")
    print(f"{'=' * 60}")

    async def _run_phase03():
        async for event in run_live_detection(checklist):
            t = event["type"]
            if t == "detection":
                print(
                    f"\n  [DETECT] Step {event['step']}: {event['title']} "
                    f"— {event['status']} (confidence: {event['confidence']:.0%})"
                )
                for comp in event.get("components_found", []):
                    print(f"           Component: {comp}")
            elif t == "verification":
                icon = "PASS" if event["complete"] else "FAIL"
                print(
                    f"  [VERIFY] Step {event['step']} attempt {event['attempt']}: "
                    f"{icon} (confidence: {event['confidence']:.0%}) — {event['reason']}"
                )
            elif t == "waiting":
                print(
                    f"  [WAIT]   Step {event['step']}: "
                    f"waiting {event['seconds']}s for user... (round {event['attempt']})"
                )
            elif t == "step_complete":
                print(f"  [DONE]   Step {event['step']}: {event['title']}")
            elif t == "step_skip":
                print(f"  [SKIP]   Step {event['step']}: {event['reason']}")
            elif t == "session_done":
                print(f"\n{event['summary']}")

    asyncio.run(_run_phase03())

    print(f"\n{'=' * 60}")


if __name__ == "__main__":
    main()
