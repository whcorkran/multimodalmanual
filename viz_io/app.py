"""
Phase 04 — Web UI for the Machine Maintenance Assistant.

FastAPI server with SSE streaming that runs the full pipeline.
Phase 03 uses the system camera via Overshoot CameraSource and streams
live detection + verification results to the browser in real time.
The browser mirrors the camera via getUserMedia and overlays annotations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Machine Maintenance Assistant")

UPLOAD_DIR = Path(tempfile.gettempdir()) / "mma_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _run_pipeline(machine_id: str, pdf_path: str | None, goal: str):
    """Generator that yields SSE events as each phase runs."""

    # --- Phase 01 ---
    title = "Manual Acquisition & Preprocessing"
    if not pdf_path:
        title += " (searching online...)"
    yield _sse_event("phase", {"phase": 1, "status": "running", "title": title})

    from phase01_intelligence.pipeline import process_manual

    manual = await asyncio.to_thread(process_manual, machine_id, pdf_path=pdf_path)

    sections_data = [
        {"title": s.title, "type": s.section_type, "pages": f"{s.page_start}-{s.page_end}"}
        for s in manual.sections
    ]
    yield _sse_event("phase01_result", {
        "machine_id": manual.machine_id,
        "source": manual.source.origin,
        "pages": len(manual.pages),
        "images": sum(len(p.image_paths) for p in manual.pages),
        "sections": sections_data,
    })
    yield _sse_event("phase", {"phase": 1, "status": "done"})

    # --- Phase 02 ---
    yield _sse_event("phase", {"phase": 2, "status": "running", "title": "Subtask Generation"})

    from subtask_generation.synthesizer import generate_subtasks

    checklist = await asyncio.to_thread(generate_subtasks, manual, goal)

    subtasks_data = [
        {
            "step": t.step_number,
            "title": t.title,
            "instruction": t.instruction,
            "priority": t.priority.value,
            "visual_cue": t.visual_cue,
            "completion_criterion": t.completion_criterion,
            "warnings": t.warnings,
            "tools": t.tools_required,
            "expected_outcome": t.expected_outcome,
        }
        for t in checklist.subtasks
    ]
    yield _sse_event("phase02_result", {
        "goal": checklist.goal,
        "safety_preamble": checklist.safety_preamble,
        "complexity": checklist.estimated_complexity,
        "subtasks": subtasks_data,
    })
    yield _sse_event("phase", {"phase": 2, "status": "done"})

    # --- Phase 03: Live camera detection ---
    yield _sse_event("phase", {"phase": 3, "status": "running", "title": "Live Detection + Verification"})

    from vlm_detection.vlm_analyzer import run_live_detection

    async for event_data in run_live_detection(checklist):
        yield _sse_event("phase03_live", event_data)

    yield _sse_event("phase", {"phase": 3, "status": "done"})
    yield _sse_event("done", {})


@app.post("/run")
async def run_pipeline(
    machine_id: str = Form(...),
    goal: str = Form(...),
    pdf: UploadFile | None = File(None),
):
    """Run the full pipeline and stream results via SSE."""
    pdf_path: str | None = None

    if pdf and pdf.filename:
        run_id = uuid.uuid4().hex[:8]
        run_dir = UPLOAD_DIR / run_id
        run_dir.mkdir()
        pdf_path = str(run_dir / pdf.filename)
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(pdf.file, f)

    return StreamingResponse(
        _run_pipeline(machine_id, pdf_path, goal),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


HTML_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Machine Maintenance Assistant</title>
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --border: #1e1e2e;
    --text: #e0e0e8;
    --muted: #6b6b80;
    --accent: #6c8cff;
    --green: #34d399;
    --amber: #fbbf24;
    --red: #f87171;
    --critical: #ef4444;
    --high: #f59e0b;
    --routine: #6b7280;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 2rem 1.5rem; }
  .container.wide { max-width: 1400px; }
  h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: 0.25rem; }
  .subtitle { color: var(--muted); font-size: 0.8rem; margin-bottom: 2rem; }

  /* Form */
  .form-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }
  .form-row { display: flex; gap: 1rem; margin-bottom: 1rem; }
  .form-row > * { flex: 1; }
  label { display: block; font-size: 0.75rem; color: var(--muted); margin-bottom: 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; }
  input[type="text"], input[type="file"] {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.6rem 0.8rem;
    color: var(--text);
    font-family: inherit;
    font-size: 0.85rem;
  }
  input[type="file"] { padding: 0.4rem 0.8rem; }
  input:focus { outline: none; border-color: var(--accent); }
  button {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 4px;
    padding: 0.7rem 2rem;
    font-family: inherit;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    margin-top: 0.5rem;
  }
  button:hover { opacity: 0.9; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Source toggle */
  .source-toggle { display: flex; gap: 0; }
  .toggle-btn {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 0.5rem 1rem;
    font-family: inherit;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    margin-top: 0;
  }
  .toggle-btn:first-child { border-radius: 4px 0 0 4px; }
  .toggle-btn:last-child { border-radius: 0 4px 4px 0; border-left: none; }
  .toggle-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
  .toggle-btn:hover:not(.active) { border-color: var(--accent); color: var(--text); }
  .search-hint {
    color: var(--muted);
    font-size: 0.8rem;
    padding: 0.6rem 0.8rem;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    line-height: 1.5;
  }

  /* Pipeline */
  #pipeline { display: none; }
  .phase {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 1rem;
    overflow: hidden;
  }
  .phase-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
  }
  .phase-num {
    background: var(--border);
    color: var(--muted);
    width: 28px; height: 28px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.75rem; font-weight: 700;
    flex-shrink: 0;
  }
  .phase-num.active { background: var(--accent); color: #fff; }
  .phase-num.done { background: var(--green); color: #000; }
  .phase-title { font-size: 0.85rem; font-weight: 600; }
  .phase-status { margin-left: auto; font-size: 0.75rem; color: var(--muted); }
  .spinner { animation: spin 1s linear infinite; display: inline-block; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .phase-body { padding: 1.25rem; font-size: 0.8rem; line-height: 1.6; display: none; }
  .phase-body.visible { display: block; }

  /* Results */
  .stat-row { display: flex; gap: 1.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
  .stat { display: flex; flex-direction: column; }
  .stat-val { font-size: 1.3rem; font-weight: 700; color: var(--accent); }
  .stat-label { font-size: 0.7rem; color: var(--muted); text-transform: uppercase; }
  .section-tag {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 3px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    margin-right: 0.4rem;
  }
  .tag-maintenance { background: #1a3a2a; color: var(--green); }
  .tag-safety { background: #3a1a1a; color: var(--red); }
  .tag-troubleshooting { background: #3a2a1a; color: var(--amber); }
  .tag-operation { background: #1a2a3a; color: var(--accent); }
  .tag-overview { background: #1e1e2e; color: var(--muted); }
  .section-list { list-style: none; }
  .section-list li { padding: 0.3rem 0; border-bottom: 1px solid var(--border); }
  .section-list li:last-child { border-bottom: none; }
  .section-pages { color: var(--muted); font-size: 0.7rem; }

  /* Safety preamble */
  .safety-box {
    background: #1a0a0a;
    border: 1px solid var(--red);
    border-radius: 4px;
    padding: 0.8rem 1rem;
    margin-bottom: 1rem;
    font-size: 0.8rem;
    color: var(--red);
  }

  /* Subtasks */
  .subtask {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    border-left: 3px solid var(--routine);
  }
  .subtask.critical { border-left-color: var(--critical); }
  .subtask.high { border-left-color: var(--high); }
  .subtask-header { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
  .subtask-step { font-weight: 700; color: var(--accent); }
  .subtask-title { font-weight: 600; }
  .priority-badge {
    margin-left: auto;
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
  }
  .priority-critical { background: #3a0a0a; color: var(--critical); }
  .priority-high { background: #3a2a0a; color: var(--high); }
  .priority-routine { background: #1e1e2e; color: var(--muted); }
  .subtask-instruction { color: var(--text); margin-bottom: 0.5rem; }
  .subtask-meta { font-size: 0.7rem; color: var(--muted); }
  .subtask-meta span { margin-right: 1rem; }
  .cue-label { color: var(--amber); }
  .done-label { color: var(--green); }
  .warn-label { color: var(--red); }

  /* === Phase 03 Live View === */
  .live-layout {
    display: grid;
    grid-template-columns: 1fr 360px;
    gap: 1.25rem;
    align-items: start;
  }
  @media (max-width: 900px) {
    .live-layout { grid-template-columns: 1fr; }
  }

  /* Video feed */
  .video-container {
    position: relative;
    background: #000;
    border-radius: 8px;
    overflow: hidden;
    aspect-ratio: 16/9;
    width: 100%;
  }
  .video-container video {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .video-container canvas {
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }
  .cam-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    font-size: 0.85rem;
    flex-direction: column;
    gap: 0.5rem;
  }
  .cam-placeholder .cam-icon { font-size: 2rem; }

  /* Step sidebar */
  .step-sidebar {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    max-height: 600px;
    overflow-y: auto;
  }

  .live-card {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    transition: border-color 0.3s, background 0.3s;
  }
  .live-card.active-step { border-color: var(--accent); background: #0d0d1a; }
  .live-card.complete-step { border-color: var(--green); }
  .live-card.skipped-step { border-color: var(--muted); opacity: 0.5; }
  .live-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.4rem;
  }
  .live-step-num {
    width: 22px; height: 22px;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.65rem; font-weight: 700;
    background: var(--border); color: var(--muted);
    flex-shrink: 0;
  }
  .live-step-num.active { background: var(--accent); color: #fff; }
  .live-step-num.done { background: var(--green); color: #000; }
  .live-step-num.skipped { background: var(--muted); color: var(--bg); }
  .live-title { font-weight: 600; font-size: 0.8rem; }
  .live-status-badge {
    margin-left: auto;
    padding: 0.1rem 0.5rem;
    border-radius: 3px;
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
  }
  .live-det, .live-ver { font-size: 0.7rem; color: var(--muted); padding: 0.2rem 0; }
  .confidence-bar {
    width: 50px; height: 5px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    display: inline-block;
    vertical-align: middle;
    margin-left: 0.3rem;
  }
  .confidence-fill { height: 100%; border-radius: 3px; }
  .live-summary {
    background: var(--surface);
    border: 1px solid var(--green);
    border-radius: 6px;
    padding: 1rem;
    margin-top: 1rem;
    font-size: 0.85rem;
    color: var(--green);
    grid-column: 1 / -1;
  }
</style>
</head>
<body>
<div class="container wide">
  <h1>Machine Maintenance Assistant</h1>
  <p class="subtitle">Upload a manual, describe your goal — AI guides you with live camera analysis.</p>

  <div class="form-card" id="formCard">
    <form id="pipelineForm">
      <div class="form-row">
        <div>
          <label>Machine ID</label>
          <input type="text" name="machine_id" placeholder="e.g. Haas VF-2 CNC Mill" required>
        </div>
        <div>
          <label>Maintenance Goal</label>
          <input type="text" name="goal" placeholder="e.g. change the oil and oil filter" required>
        </div>
      </div>
      <div class="form-row">
        <div>
          <label>Manual Source</label>
          <div class="source-toggle">
            <button type="button" class="toggle-btn active" id="toggleUpload" onclick="setSource('upload')">Upload PDF</button>
            <button type="button" class="toggle-btn" id="toggleSearch" onclick="setSource('search')">Find Online</button>
          </div>
        </div>
      </div>
      <div class="form-row" id="uploadRow">
        <div>
          <label>PDF Manual</label>
          <input type="file" name="pdf" accept=".pdf" id="pdfInput">
        </div>
      </div>
      <div class="form-row" id="searchRow" style="display:none">
        <div class="search-hint">
          The system will search for a PDF manual online using the Machine ID above.
          Requires Browserbase credentials to be configured.
        </div>
      </div>
      <button type="submit" id="submitBtn">Start Live Session</button>
    </form>
  </div>

  <div id="pipeline">
    <div class="phase" id="phase1">
      <div class="phase-header">
        <div class="phase-num" id="phase1Num">1</div>
        <span class="phase-title">Manual Acquisition & Preprocessing</span>
        <span class="phase-status" id="phase1Status"></span>
      </div>
      <div class="phase-body" id="phase1Body"></div>
    </div>
    <div class="phase" id="phase2">
      <div class="phase-header">
        <div class="phase-num" id="phase2Num">2</div>
        <span class="phase-title">Subtask Generation</span>
        <span class="phase-status" id="phase2Status"></span>
      </div>
      <div class="phase-body" id="phase2Body"></div>
    </div>
    <div class="phase" id="phase3">
      <div class="phase-header">
        <div class="phase-num" id="phase3Num">3</div>
        <span class="phase-title">Live Detection + Verification</span>
        <span class="phase-status" id="phase3Status"></span>
      </div>
      <div class="phase-body" id="phase3Body"></div>
    </div>
  </div>
</div>

<script>
const form = document.getElementById('pipelineForm');
const btn = document.getElementById('submitBtn');
const pipeline = document.getElementById('pipeline');

let subtasksList = [];
let manualSource = 'upload';

function setSource(mode) {
  manualSource = mode;
  document.getElementById('toggleUpload').classList.toggle('active', mode === 'upload');
  document.getElementById('toggleSearch').classList.toggle('active', mode === 'search');
  document.getElementById('uploadRow').style.display = mode === 'upload' ? '' : 'none';
  document.getElementById('searchRow').style.display = mode === 'search' ? '' : 'none';
  const pdfInput = document.getElementById('pdfInput');
  if (mode === 'search') pdfInput.value = '';
}

let currentStep = null;
let currentDetection = null;
let currentVerification = null;
let completedSteps = new Set();
let skippedSteps = new Set();
let overlayCanvas = null;
let overlayCtx = null;
let overlayRAF = null;

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  btn.disabled = true;
  btn.textContent = 'Streaming...';
  pipeline.style.display = 'block';
  subtasksList = [];
  currentStep = null;
  currentDetection = null;
  currentVerification = null;
  completedSteps = new Set();
  skippedSteps = new Set();

  for (let i = 1; i <= 3; i++) {
    document.getElementById(`phase${i}Num`).className = 'phase-num';
    document.getElementById(`phase${i}Status`).textContent = '';
    const body = document.getElementById(`phase${i}Body`);
    body.innerHTML = '';
    body.classList.remove('visible');
  }

  const fd = new FormData(form);
  const resp = await fetch('/run', { method: 'POST', body: fd });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let lines = buffer.split('\\n');
    buffer = lines.pop();

    let eventType = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7);
      } else if (line.startsWith('data: ') && eventType) {
        try {
          handleEvent(eventType, JSON.parse(line.slice(6)));
        } catch {}
        eventType = '';
      }
    }
  }

  stopOverlay();
  btn.disabled = false;
  btn.textContent = 'Start Live Session';
});

function handleEvent(event, data) {
  if (event === 'phase') {
    const num = document.getElementById(`phase${data.phase}Num`);
    const status = document.getElementById(`phase${data.phase}Status`);
    if (data.status === 'running') {
      num.className = 'phase-num active';
      status.innerHTML = '<span class="spinner">&#9881;</span> Running...';
      if (data.phase === 3) {
        document.querySelector('.container').classList.add('wide');
        startCamera();
      }
    } else if (data.status === 'done') {
      num.className = 'phase-num done';
      status.textContent = 'Complete';
      if (data.phase === 3) stopCamera();
    }
  }
  if (event === 'phase01_result') renderPhase01(data);
  if (event === 'phase02_result') renderPhase02(data);
  if (event === 'phase03_live') renderPhase03Live(data);
}

/* --- Camera --- */
let camStream = null;

async function startCamera() {
  const video = document.getElementById('camVideo');
  const placeholder = document.getElementById('camPlaceholder');
  if (!video) return;
  try {
    camStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' }
    });
    video.srcObject = camStream;
    video.play();
    if (placeholder) placeholder.style.display = 'none';

    overlayCanvas = document.getElementById('camOverlay');
    overlayCtx = overlayCanvas.getContext('2d');
    startOverlay();
  } catch (err) {
    console.warn('Camera access denied:', err);
    if (placeholder) placeholder.textContent = 'Camera access denied';
  }
}

function stopCamera() {
  if (camStream) {
    camStream.getTracks().forEach(t => t.stop());
    camStream = null;
  }
}

/* --- Overlay rendering --- */
function startOverlay() {
  if (overlayRAF) return;
  function draw() {
    overlayRAF = requestAnimationFrame(draw);
    if (!overlayCanvas || !overlayCtx) return;

    const W = overlayCanvas.clientWidth;
    const H = overlayCanvas.clientHeight;
    overlayCanvas.width = W * devicePixelRatio;
    overlayCanvas.height = H * devicePixelRatio;
    overlayCtx.scale(devicePixelRatio, devicePixelRatio);

    overlayCtx.clearRect(0, 0, W, H);

    // Semi-transparent top bar
    overlayCtx.fillStyle = 'rgba(0,0,0,0.55)';
    overlayCtx.fillRect(0, 0, W, 52);

    // Current step title
    if (currentStep !== null) {
      const task = subtasksList.find(t => t.step === currentStep);
      if (task) {
        overlayCtx.font = '600 16px SF Mono, Consolas, monospace';
        overlayCtx.fillStyle = '#6c8cff';
        overlayCtx.fillText(`Step ${task.step}`, 14, 22);

        overlayCtx.font = '600 14px SF Mono, Consolas, monospace';
        overlayCtx.fillStyle = '#e0e0e8';
        overlayCtx.fillText(task.title, 14, 42);
      }
    }

    // Detection status indicator (top right)
    if (currentDetection) {
      const statusColors = { ready: '#34d399', unclear: '#fbbf24', problem: '#f87171' };
      const color = statusColors[currentDetection.status] || '#fbbf24';
      const confPct = Math.round(currentDetection.confidence * 100);

      // Status dot
      overlayCtx.beginPath();
      overlayCtx.arc(W - 30, 26, 10, 0, Math.PI * 2);
      overlayCtx.fillStyle = color;
      overlayCtx.fill();

      // Status text
      overlayCtx.font = '700 12px SF Mono, Consolas, monospace';
      overlayCtx.fillStyle = color;
      overlayCtx.textAlign = 'right';
      overlayCtx.fillText(currentDetection.status.toUpperCase() + ' ' + confPct + '%', W - 48, 22);

      // Components
      if (currentDetection.components && currentDetection.components.length) {
        overlayCtx.font = '11px SF Mono, Consolas, monospace';
        overlayCtx.fillStyle = '#a0a0b0';
        overlayCtx.fillText(currentDetection.components.join(', '), W - 48, 40);
      }
      overlayCtx.textAlign = 'left';
    }

    // Verification banner (bottom)
    if (currentVerification) {
      const isComplete = currentVerification.complete;
      const bannerColor = isComplete ? 'rgba(16, 80, 50, 0.85)' : 'rgba(80, 20, 20, 0.85)';
      const borderColor = isComplete ? '#34d399' : '#f87171';
      const bannerH = 50;
      const bannerY = H - bannerH;

      overlayCtx.fillStyle = bannerColor;
      overlayCtx.fillRect(0, bannerY, W, bannerH);
      overlayCtx.strokeStyle = borderColor;
      overlayCtx.lineWidth = 2;
      overlayCtx.beginPath();
      overlayCtx.moveTo(0, bannerY);
      overlayCtx.lineTo(W, bannerY);
      overlayCtx.stroke();

      const icon = isComplete ? 'COMPLETE' : 'INCOMPLETE';
      const confPct = Math.round(currentVerification.confidence * 100);

      overlayCtx.font = '700 14px SF Mono, Consolas, monospace';
      overlayCtx.fillStyle = borderColor;
      overlayCtx.fillText(icon + '  (' + confPct + '%)', 14, bannerY + 22);

      if (currentVerification.reason) {
        overlayCtx.font = '12px SF Mono, Consolas, monospace';
        overlayCtx.fillStyle = '#d0d0d8';
        overlayCtx.fillText(currentVerification.reason, 14, bannerY + 40);
      }
    }

    // Progress pips (bottom-right)
    if (subtasksList.length) {
      const pipSize = 12;
      const pipGap = 6;
      const totalW = subtasksList.length * (pipSize + pipGap) - pipGap;
      let px = W - totalW - 14;
      const py = H - 62;

      for (const t of subtasksList) {
        overlayCtx.beginPath();
        overlayCtx.roundRect(px, py, pipSize, pipSize, 2);
        if (completedSteps.has(t.step)) {
          overlayCtx.fillStyle = '#34d399';
        } else if (skippedSteps.has(t.step)) {
          overlayCtx.fillStyle = '#6b6b80';
        } else if (t.step === currentStep) {
          overlayCtx.fillStyle = '#6c8cff';
        } else {
          overlayCtx.fillStyle = '#1e1e2e';
        }
        overlayCtx.fill();
        overlayCtx.strokeStyle = '#333';
        overlayCtx.lineWidth = 1;
        overlayCtx.stroke();
        px += pipSize + pipGap;
      }
    }
  }
  draw();
}

function stopOverlay() {
  if (overlayRAF) {
    cancelAnimationFrame(overlayRAF);
    overlayRAF = null;
  }
}

/* --- Phase renderers --- */
function renderPhase01(d) {
  const body = document.getElementById('phase1Body');
  const tagClass = t => 'tag-' + (t || 'overview');
  body.innerHTML = `
    <div class="stat-row">
      <div class="stat"><span class="stat-val">${d.pages}</span><span class="stat-label">Pages</span></div>
      <div class="stat"><span class="stat-val">${d.images}</span><span class="stat-label">Images</span></div>
      <div class="stat"><span class="stat-val">${d.sections.length}</span><span class="stat-label">Sections</span></div>
    </div>
    <ul class="section-list">
      ${d.sections.map(s => `
        <li>
          <span class="section-tag ${tagClass(s.type)}">${s.type || 'other'}</span>
          ${esc(s.title)}
          <span class="section-pages">pp. ${s.pages}</span>
        </li>
      `).join('')}
    </ul>`;
  body.classList.add('visible');
}

function renderPhase02(d) {
  const body = document.getElementById('phase2Body');
  subtasksList = d.subtasks;
  const safetyHtml = d.safety_preamble
    ? `<div class="safety-box">${esc(d.safety_preamble)}</div>` : '';

  body.innerHTML = `
    ${safetyHtml}
    <div class="stat-row">
      <div class="stat"><span class="stat-val">${d.subtasks.length}</span><span class="stat-label">Subtasks</span></div>
      <div class="stat"><span class="stat-val">${d.complexity}</span><span class="stat-label">Complexity</span></div>
    </div>
    ${d.subtasks.map(t => `
      <div class="subtask ${t.priority}">
        <div class="subtask-header">
          <span class="subtask-step">#${t.step}</span>
          <span class="subtask-title">${esc(t.title)}</span>
          <span class="priority-badge priority-${t.priority}">${t.priority}</span>
        </div>
        <div class="subtask-instruction">${esc(t.instruction)}</div>
        <div class="subtask-meta">
          ${t.visual_cue ? `<span class="cue-label">Eye: ${esc(t.visual_cue)}</span><br>` : ''}
          ${t.completion_criterion ? `<span class="done-label">Done: ${esc(t.completion_criterion)}</span><br>` : ''}
          ${t.warnings.length ? t.warnings.map(w => `<span class="warn-label">Warning: ${esc(w)}</span><br>`).join('') : ''}
          ${t.tools.length ? `<span>Tools: ${t.tools.map(esc).join(', ')}</span>` : ''}
        </div>
      </div>
    `).join('')}`;
  body.classList.add('visible');

  // Pre-build Phase 03 live layout: video + sidebar
  const p3body = document.getElementById('phase3Body');
  p3body.innerHTML = `
    <div class="live-layout">
      <div>
        <div class="video-container">
          <video id="camVideo" autoplay muted playsinline></video>
          <canvas id="camOverlay"></canvas>
          <div class="cam-placeholder" id="camPlaceholder">
            <span class="cam-icon">&#128247;</span>
            Waiting for camera...
          </div>
        </div>
      </div>
      <div class="step-sidebar" id="stepSidebar">
        ${d.subtasks.map(t => `
          <div class="live-card" id="live-step-${t.step}">
            <div class="live-header">
              <div class="live-step-num" id="live-num-${t.step}">${t.step}</div>
              <span class="live-title">${esc(t.title)}</span>
              <span class="live-status-badge" id="live-badge-${t.step}" style="display:none"></span>
            </div>
            <div class="live-det" id="live-det-${t.step}"></div>
            <div class="live-ver" id="live-ver-${t.step}"></div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  p3body.classList.add('visible');
}

function renderPhase03Live(d) {
  const t = d.type;

  if (t === 'detection') {
    const card = document.getElementById(`live-step-${d.step}`);
    const num = document.getElementById(`live-num-${d.step}`);
    const det = document.getElementById(`live-det-${d.step}`);
    if (!card) return;

    currentStep = d.step;
    currentDetection = {
      status: d.status,
      confidence: d.confidence,
      components: d.components_found || [],
    };
    currentVerification = null;

    card.className = 'live-card active-step';
    num.className = 'live-step-num active';

    const statusColor = d.status === 'ready' ? 'var(--green)'
      : d.status === 'problem' ? 'var(--red)' : 'var(--amber)';
    const confPct = Math.round(d.confidence * 100);
    const confColor = confPct > 70 ? 'var(--green)' : confPct > 40 ? 'var(--amber)' : 'var(--red)';

    det.innerHTML = `
      <span style="color:${statusColor};font-weight:600">${d.status}</span>
      &middot; ${(d.components_found || []).map(esc).join(', ') || 'scanning...'}
      <div class="confidence-bar"><div class="confidence-fill" style="width:${confPct}%;background:${confColor}"></div></div> ${confPct}%
    `;

    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  if (t === 'verification') {
    const ver = document.getElementById(`live-ver-${d.step}`);
    if (!ver) return;

    currentVerification = {
      complete: d.complete,
      confidence: d.confidence,
      reason: d.reason || '',
    };

    const confPct = Math.round(d.confidence * 100);
    const confColor = confPct > 70 ? 'var(--green)' : confPct > 40 ? 'var(--amber)' : 'var(--red)';
    const icon = d.complete ? '&#9989;' : '&#10060;';

    ver.innerHTML = `
      ${icon}
      ${d.complete ? '<span style="color:var(--green);font-weight:600">COMPLETE</span>' : '<span style="color:var(--red)">INCOMPLETE</span>'}
      <div class="confidence-bar"><div class="confidence-fill" style="width:${confPct}%;background:${confColor}"></div></div> ${confPct}%
      &middot; ${esc(d.reason)}
    `;
  }

  if (t === 'step_complete') {
    const card = document.getElementById(`live-step-${d.step}`);
    const num = document.getElementById(`live-num-${d.step}`);
    const badge = document.getElementById(`live-badge-${d.step}`);
    if (!card) return;

    completedSteps.add(d.step);
    card.className = 'live-card complete-step';
    num.className = 'live-step-num done';
    badge.style.display = 'inline-block';
    badge.style.background = '#0a2a1a';
    badge.style.color = 'var(--green)';
    badge.textContent = 'DONE';

    currentVerification = { complete: true, confidence: 1, reason: 'Step complete' };
    setTimeout(() => { currentVerification = null; }, 2000);
  }

  if (t === 'waiting') {
    const ver = document.getElementById(`live-ver-${d.step}`);
    if (!ver) return;
    ver.innerHTML += `
      <br><span style="color:var(--amber)">Waiting ${d.seconds}s... (round ${d.attempt})</span>
    `;
  }

  if (t === 'step_skip') {
    const card = document.getElementById(`live-step-${d.step}`);
    const num = document.getElementById(`live-num-${d.step}`);
    const badge = document.getElementById(`live-badge-${d.step}`);
    const det = document.getElementById(`live-det-${d.step}`);
    if (!card) return;

    skippedSteps.add(d.step);
    card.className = 'live-card skipped-step';
    num.className = 'live-step-num skipped';
    badge.style.display = 'inline-block';
    badge.style.background = '#1e1e2e';
    badge.style.color = 'var(--muted)';
    badge.textContent = 'SKIP';
    det.innerHTML = `<span style="color:var(--muted)">${esc(d.reason)}</span>`;
  }

  if (t === 'session_done') {
    const body = document.getElementById('phase3Body');
    const doneCount = (d.completed || []).filter(c => c.complete).length;
    const total = (d.completed || []).length + (d.skipped || []).length;
    body.innerHTML += `
      <div class="live-summary">
        Session complete: ${esc(d.summary)}<br>
        ${doneCount}/${total} steps verified complete.
      </div>
    `;
    currentStep = null;
    currentDetection = null;
    currentVerification = null;
  }
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
</script>
</body>
</html>
"""
