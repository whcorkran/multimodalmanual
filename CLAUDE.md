# Machine Maintenance Assistant

AI-powered tool that guides users through machine maintenance using visual inference, manual parsing, and real-time AR-style overlays with audio instructions.

Full spec: `machine-maintenance-pipeline.md`

## Tech Stack

- **Python 3.13+** (uv-managed)
- **Browserbase + Playwright** — web search for PDF manuals
- **PyMuPDF** — PDF text and image extraction
- **Overshoot VLM** — visual language model for state detection and real-time component recognition
- **TTS** — text-to-speech for hands-free audio guidance
- **WebRTC** — live camera stream capture
- **Canvas/AR layer** — bounding box overlay rendering on live feed

## Architecture

### Phase 01 — Manual Acquisition & Preprocessing [DONE]
Two input paths, same output:
- **Upload**: user provides a local PDF
- **Web search**: Browserbase crawls for `filetype:pdf` manuals (2-min timeout)

Both paths feed into the same preprocessing pipeline:
- Parse PDF with PyMuPDF: extract per-page text + images
- Classify sections by heading detection + keyword matching (safety, maintenance, troubleshooting, operation, overview)
- Output: `ProcessedManual` with pages, images, and labeled sections

### Phase 02 — Visual State Detection (Overshoot VLM)
- Accept live camera feeds, uploaded photos, or manual images
- Run Overshoot inference with manual-derived context
- Classify component anomalies by location, severity, and confidence
- Output: `AnnotatedStateReport`

### Phase 03 — Subtask Generation (LLM Synthesis)
- Match VLM findings to manual procedures
- Decompose into granular step-level subtasks
- Sequence respecting safety constraints and dependencies
- Tag priority: Critical / High / Routine
- Output: `PrioritizedSubtaskChecklist`

### Phase 04 — Guided Execution & Feedback Loop
- Stream live camera via WebRTC
- Deliver step-by-step audio prompts via TTS
- Run Overshoot inference on live frames with active subtask as context
- Render bounding box overlays (green=done, amber=pending, red=problem)
- Loop per subtask until confirmed complete
- Generate session completion log

## Project Structure

```
multimodalmanual/
  main.py                           # CLI entry point
  config/
    settings.py                     # Env-based settings (API keys, timeouts)
  models/
    machine_knowledge.py            # ProcessedManual, ManualSection, ManualPage, etc.
  phase01_intelligence/
    crawler.py                      # Browserbase PDF search + download
    pipeline.py                     # Unified acquire -> parse -> classify orchestrator
  doc_preprocessing/
    pdf_parser.py                   # PyMuPDF text + image extraction
    section_classifier.py           # Heading detection + section type classification
  overshoot/                        # Phase 02 — VLM inference (planned)
  viz_io/                           # Phase 04 — camera/overlay IO (planned)
```

## Usage

```bash
# Process a local PDF:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf

# Search the web for a manual:
uv run python main.py "Haas VF-2 CNC Mill"
```

## Conventions

- Use uv for dependency management
- Shared data models in `models/`
- Type hints throughout
- Phases are loosely coupled via shared Pydantic models
