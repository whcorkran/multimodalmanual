"""
Machine Maintenance Assistant — Pipeline Orchestrator

Acquires and preprocesses a machine's operating manual, producing
structured data (pages, images, classified sections) for the VLM.

Usage:
    # Search the web for a manual:
    uv run python main.py "Haas VF-2 CNC Mill"

    # Use a local PDF:
    uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

from phase01_intelligence.pipeline import process_manual, save_processed_manual


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Machine Maintenance Assistant — acquire and preprocess operating manual",
    )
    parser.add_argument(
        "machine_id",
        help="Machine name, model number, or serial (e.g. 'Haas VF-2 CNC Mill')",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help="Path to a local PDF manual (skips web search)",
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

    manual = process_manual(args.machine_id, pdf_path=args.pdf)

    # Summary
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


if __name__ == "__main__":
    main()
