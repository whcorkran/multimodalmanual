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

### Inputs
1. **Manual** — either a local PDF upload or a web-crawled PDF (see Phase 01)
2. **User goal prompt** — natural language description of the task (e.g. `"change the oil and oil filter"`)

The goal prompt is a **first-class input** that threads through Phases 02, 03, and 04. It is not just a label — it directly shapes VLM context windows at every inference call.

### Phase 01 — Manual Acquisition & Preprocessing [DONE]
Two input paths, same output:
- **Upload**: user provides a local PDF
- **Web search**: Browserbase crawls for `filetype:pdf` manuals (2-min timeout)

Both paths feed into the same preprocessing pipeline:
- Parse PDF with PyMuPDF: extract per-page text + images
- Classify sections by heading detection + keyword matching (safety, maintenance, troubleshooting, operation, overview)
- Output: `ProcessedManual` with pages, images, and labeled sections

### Phase 02 — Goal-Aware Subtask Generation (LLM Synthesis)

**Inputs:** `ProcessedManual` + User goal prompt

**Process:**
- LLM reads the relevant manual sections filtered by goal (e.g. maintenance + safety)
- Decomposes the goal into granular, sequenced subtasks
- Each subtask is tagged with:
  - **Priority**: Critical / High / Routine
  - **Visual cue**: what the camera should look for (e.g. `"oil drain plug on underside of engine block"`)
  - **Completion criterion**: what constitutes done (e.g. `"new oil filter fully seated, no cross-threading"`)
  - **Safety constraints**: predecessor steps that must be confirmed first

**Output:** `PrioritizedSubtaskChecklist` — an ordered list of `Subtask` objects, each carrying its own VLM prompt fragments for use downstream

### Phase 03 — Goal-Aware Detection + Guided Execution Loop (Overshoot VLM)

For each `Subtask` in the checklist, the following loop runs:

#### Step A — Targeted Component Detection
- Overshoot receives the **current subtask's visual cue** as context (not a generic anomaly prompt)
  - Example context: `"Locate the oil drain plug. It is typically a hex-head bolt on the underside of the oil pan."`
- Overshoot runs inference on the live camera frame
- Returns bounding boxes + confidence scores for relevant components
- Overlay renders on the AR canvas:
  - 🟢 Green — component identified, ready to act
  - 🟡 Amber — component located but condition unclear
  - 🔴 Red — problem detected (e.g. stripped bolt, wrong component)

#### Step B — Audio Instruction Delivery
- TTS reads the subtask instruction aloud, referencing the detected component location
- User performs the physical step hands-free

#### Step C — Completion Verification (Second VLM Agent)
- A **separate Overshoot inference pass** runs after the user signals readiness (voice command or gesture)
- This call uses the subtask's **completion criterion** as its prompt — not the detection prompt
  - Example: `"Confirm the drain plug is reinstalled and torqued. Look for flush seating and no visible oil seepage around the plug."`
- Returns: `CompletionVerdict { complete: bool, confidence: float, reason: str }`
- If `complete=False`: TTS reads the `reason`, overlay highlights the issue, loop repeats from Step B
- If `complete=True`: subtask is marked done, next subtask begins

```
for subtask in checklist:
    while True:
        frame = capture_frame()
        detection = overshoot.detect(frame, context=subtask.visual_cue)
        render_overlay(detection)
        tts.speak(subtask.instruction)
        wait_for_user_ready()
        frame = capture_frame()
        verdict = overshoot.verify(frame, criterion=subtask.completion_criterion)
        if verdict.complete:
            log_subtask_complete(subtask, verdict)
            break
        else:
            tts.speak(f"Not quite: {verdict.reason}")
```

**Why two separate VLM calls?**

Detection and verification are fundamentally different questions:
- **Detection** asks: *"Where is the thing I need to interact with?"* — forward-looking, spatial
- **Verification** asks: *"Has the action been successfully completed?"* — backward-looking, evaluative

Using a single prompt for both degrades accuracy on both tasks. Separate calls with targeted prompts produce cleaner, more actionable outputs.

#### Output
- `SessionLog` with per-subtask completion timestamps, confidence scores, and any retry events


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
  subtask_generation/
    synthesizer.py                  # Phase 02 — LLM subtask generation (Anthropic)
  overshoot/
    vlm_analyzer.py                 # Phase 03 — VLM detection + verification (Overshoot)
  viz_io/                           # Phase 04 — camera/overlay IO (planned)
```

## Usage

```bash
# Phase 01 only — process a local PDF:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --phase 1

# Phases 01-02 — generate subtask checklist:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil"

# Full pipeline (01-03) — with VLM detection on an image:
uv run python main.py "Haas VF-2 CNC Mill" --pdf manual.pdf --goal "change the oil" --image photo.jpg
```

## Conventions

- Use uv for dependency management
- Shared data models in `models/`
- Type hints throughout
- Phases are loosely coupled via shared Pydantic models
