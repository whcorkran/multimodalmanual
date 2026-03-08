# Maintenance Assistant

AI-powered tool that guides users through machine maintenance using visual inference, manual parsing, and real-time camera overlays with step-by-step instructions.

Given a product manual and a maintenance goal, the system decomposes the task into subtasks, then uses a vision-language model on a live camera feed to detect relevant components and verify each step as the user completes it.

## Architecture

The pipeline has four phases, each loosely coupled via shared Pydantic models:

```
                  +------------------+
                  |   User Inputs    |
                  |  Manual + Goal   |
                  +--------+---------+
                           |
                  Phase 01 | Manual Acquisition
                           |
                  +--------v---------+
                  |  ProcessedManual |
                  |  pages, sections |
                  +--------+---------+
                           |
                  Phase 02 | Subtask Generation (Gemini LLM)
                           |
                  +--------v---------+
                  | SubtaskChecklist |
                  | visual_cue +     |
                  | completion_crit  |
                  +--------+---------+
                           |
                  Phase 03 | Live Detection + Verification (Overshoot VLM)
                           |
                  +--------v---------+
                  |   SessionLog     |
                  |  per-step results|
                  +------------------+
```

### Phase 01 -- Manual Acquisition & Preprocessing

Two input paths, same output:

- **Upload**: user provides a local PDF
- **Web search**: Browserbase + Playwright crawls Google for `filetype:pdf` manuals matching the product name (2-minute timeout, 5 query variants)

Both paths feed into:

1. **PDF parsing** (PyMuPDF) -- extract per-page text and images (filtering out icons < 100px)
2. **Section classification** -- heading detection via regex + keyword matching into five types: safety, maintenance, troubleshooting, operation, overview

Output: `ProcessedManual` with pages, images, and labeled sections.

### Phase 02 -- Goal-Aware Subtask Generation

Uses Google Gemini to decompose the user's goal into ordered subtasks given the manual content.

Each subtask carries its own VLM prompt fragments for Phase 03:

- **visual_cue** -- what the camera should look for during detection (e.g. "oil drain plug on underside of engine block")
- **completion_criterion** -- what "done" looks like for verification (e.g. "new oil filter fully seated, no cross-threading")
- **safety_prerequisites** -- step numbers that must complete first
- Priority, warnings, required tools

Output: `PrioritizedSubtaskChecklist` with a safety preamble and complexity estimate.

### Phase 03 -- Live Detection & Verification Loop

Opens a single persistent camera stream via Overshoot VLM. For each subtask:

1. **Detection** -- VLM receives the subtask's `visual_cue` as context, identifies components in the frame, returns status (ready / unclear / problem) with confidence
2. **Verification** -- after the user acts, a separate VLM call uses the `completion_criterion` to check if the step is done
3. If incomplete, the loop waits and retries; if complete, moves to the next subtask

Detection and verification use separate prompts because they ask fundamentally different questions -- "where is the thing?" (spatial) vs. "was the action successful?" (evaluative). A unified JSON schema with a `mode` discriminator allows both to share a single stream.

Output: `SessionLog` with per-subtask detection results, completion verdicts, and retry counts.

### Phase 04 -- Web UI

FastAPI server streaming all phases via Server-Sent Events (SSE). The browser:

- Mirrors the local camera via `getUserMedia` (same physical camera Overshoot reads server-side)
- Renders a canvas overlay with current step info, detection status (green/amber/red), verification banners, and progress pips
- Shows a step sidebar tracking each subtask's state in real time

## Project Structure

```
multimodalmanual/
  main.py                             # CLI entry point + web server launcher
  config/
    settings.py                       # Env-based config (API keys, timeouts, model names)
  models/
    machine_knowledge.py              # Shared Pydantic models across all phases
  doc_preprocessing/
    pdf_parser.py                     # PyMuPDF text + image extraction
    section_classifier.py             # Heading detection + section type classification
  phase01_intelligence/
    crawler.py                        # Browserbase PDF search + download
    pipeline.py                       # Orchestrator: acquire -> parse -> classify
  subtask_generation/
    synthesizer.py                    # Gemini LLM subtask decomposition
  vlm_detection/
    vlm_analyzer.py                   # Overshoot VLM detection + verification loop
  viz_io/
    app.py                            # FastAPI web UI with SSE + camera overlay
```

## Setup

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### Environment Variables

Create a `.env` file:

```
GEMINI_API_KEY=...
OVERSHOOT_API_KEY=...

# Only needed for web search (optional if uploading PDFs):
BROWSERBASE_API_KEY=...
BROWSERBASE_PROJECT_ID=...
```

Optional overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `OVERSHOOT_MODEL` | `Qwen/Qwen3.5-9B` | VLM model for detection/verification |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite-preview` | LLM for subtask generation |

## Usage

```bash
# Phase 01 only -- process a local PDF:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --phase 1

# Phases 01-02 -- generate subtask checklist:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil"

# Full pipeline (01-03) -- live camera detection:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil"

# Web UI:
uv run python main.py --serve
```

### CLI Options

| Flag | Description |
|------|-------------|
| `machine_id` | Product name or model number |
| `--pdf PATH` | Local PDF (skip web search) |
| `--goal TEXT` | Maintenance goal (required for Phase 02+) |
| `--phase 1\|2\|3` | Run up to this phase (default: 3) |
| `--serve` | Launch web UI instead of CLI |
| `--port N` | Web UI port (default: 8000) |
| `-o PATH` | Output path for processed manual JSON |
| `-v` | Verbose logging |
