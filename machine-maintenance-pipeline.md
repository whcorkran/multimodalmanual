# Machine Maintenance Assistant — Full Pipeline Spec

**Version:** 1.0  
**Status:** Draft  

---

## Overview

The Machine Maintenance Assistant is an end-to-end AI-powered tool that helps users safely and accurately perform maintenance on any machine. Rather than relying on a technician's prior knowledge or hunting through manuals, the system automatically researches the target machine, reads its current physical state through a camera, cross-references the user's guide, and then walks the user through every maintenance step in real time — using audio instructions and live visual overlays drawn directly onto the machine in view.

The result is a guided, hands-free maintenance experience that adapts to what is actually happening in front of the user, closing the loop after every step until the full task is confirmed complete.

---

## How It Works — Pipeline Summary

```
Machine ID Input
      │
      ▼
Phase 01 — Browserbase Web Scraper
      │  Machine Knowledge Base
      ▼
Phase 02 — Overshoot VLM Inference
      │  Annotated State Report
      ▼
Phase 03 — User Guide Parser
      │  Indexed Procedure Library
      ▼
Phase 04 — Subtask Generator
      │  Prioritized Subtask Checklist
      ▼
Phase 05 — Guided Execution & Feedback Loop
      │  Verified Session Completion Log
      ▼
     Done
```

---

## Phase 01 — Machine Intelligence Gathering
**Tool:** Browserbase Web Scraper

### Purpose
Before any maintenance can begin, the system needs to understand the machine. Phase 01 uses Browserbase to automatically crawl the web and build a comprehensive knowledge base for the target machine — pulling specs, error codes, maintenance schedules, diagrams, and reference images. This knowledge base feeds every downstream phase.

### Tasks

**1a · Machine Identification Input**  
Accept machine name, model number, or serial as the starting query. This is the entry point for the entire pipeline — the identifier seeds all Browserbase crawl sessions.

- Accepts machine name (e.g. "Haas VF-2 CNC Mill"), model number, serial number, or a combination

**1b · Browserbase Crawler Setup**  
Configure Browserbase sessions to navigate manufacturer sites, forums, spec sheets, and documentation portals.

- Target sources: manufacturer product and support pages, technical forums, third-party spec aggregators, parts suppliers, service bulletins

**1c · Structured Data Extraction**  
Pull specs, known issues, maintenance schedules, part numbers, wiring diagrams, and error code tables.

- Extracts: technical specifications, maintenance intervals, error/fault code tables, wiring and pneumatic diagrams, known failure modes

**1d · Image Asset Collection**  
Gather machine images, diagrams, and component photos for downstream VLM analysis. Images collected here are passed to Overshoot in Phase 02 as reference context, grounding inference in accurate component visuals.

- Asset types: external machine views, internal component diagrams, control panel layouts, annotated part diagrams

**1e · Data Normalization**  
Deduplicate and structure all scraped data into a unified machine knowledge object consumable by Phase 02 and Phase 03.

- Output schema: `machine_id`, `specs`, `error_codes`, `maintenance`, `images`, `sources`

### Output
> **Machine Knowledge Base** — a normalized object containing specs, documentation, error codes, maintenance data, and labeled image assets.

---

## Phase 02 — Visual State Detection
**Tool:** Overshoot VLM Inference

### Purpose
Once the system knows what the machine should look like, it needs to understand what it actually looks like right now. Phase 02 sends machine images through Overshoot — a VLM inference tool — to detect the current physical state: anomalies, wear, error indicators, misalignments, and any visible issues that will inform the maintenance plan.

### Tasks

**2a · Image Input Pipeline**  
Accept live camera feeds, uploaded photos, or images pulled by Browserbase in Phase 01 as input to Overshoot.

**2b · Overshoot Inference Call**  
Send images to Overshoot with contextual prompts derived from the machine knowledge base (e.g. "What is the state of the control panel on this Haas VF-2?"). Knowledge base context makes prompts machine-specific rather than generic.

**2c · Component State Classification**  
Detect visible anomalies: leaks, wear, incorrect settings, error indicators, misalignments, or damage. Classify each finding by component and severity.

**2d · Region-of-Interest Annotation**  
Map detected issues to specific machine regions with bounding context. Output structured annotations that Phase 04 can use to prioritize and sequence subtasks.

**2e · Confidence Scoring & Flagging**  
Score each detection. Flag low-confidence findings for human review before they influence task generation.

### Output
> **Annotated State Report** — a structured list of detected issues with component location, severity, and confidence score.

---

## Phase 03 — User Guide Parsing
**Tool:** Document Intelligence Layer

### Purpose
The user uploads their machine's official user guide or service manual. Phase 03 parses this document to extract every relevant procedure, safety warning, and decision tree — then indexes them by symptom so they can be matched against the VLM's findings in Phase 04.

### Tasks

**3a · Guide Upload & Ingestion**  
Accept PDF, DOCX, or image-based user manuals as input.

**3b · Section & Procedure Extraction**  
Identify chapters covering maintenance, troubleshooting, operation, and safety. Extract each as a discrete, labeled section.

**3c · Procedure Decomposition**  
Break each procedure into discrete, ordered steps with tools required, warnings, and expected outcomes.

**3d · Symptom-to-Procedure Mapping**  
Build an index linking observed symptoms or component states to relevant guide sections. This is what enables Phase 04 to match VLM findings to actionable procedures.

**3e · Guide + Machine KB Alignment**  
Cross-reference parsed procedures against the Phase 01 knowledge base to resolve conflicts, fill gaps, and flag any discrepancies between the guide and manufacturer documentation.

### Output
> **Indexed Procedure Library** — a symptom-keyed index mapping observed states to ordered, guide-grounded procedures.

---

## Phase 04 — Subtask Generation
**Tool:** Synthesis & Task Planning

### Purpose
With the machine's state known (Phase 02) and the guide's procedures indexed (Phase 03), Phase 04 matches findings to procedures and decomposes them into a prioritized, sequenced list of subtasks. This is the maintenance plan the user will be guided through in Phase 05.

### Tasks

**4a · State × Procedure Matching**  
Match each detected issue from the Phase 02 annotated report to the most relevant procedure in the Phase 03 index.

**4b · Subtask Decomposition**  
Expand matched procedures into granular, step-level subtasks with tool requirements and safety notes at each step.

**4c · Dependency & Sequencing**  
Order subtasks respecting safety constraints, physical access order, and procedural dependencies (e.g. power down before disassembly, drain fluid before removing a component).

**4d · Priority & Urgency Tagging**  
Tag each subtask as Critical / High / Routine based on detected severity and guide safety classifications.

**4e · Output Formatting**  
Render the final subtask list as a structured checklist, exportable to JSON, PDF, or external ticket systems.

### Output
> **Prioritized Subtask Checklist** — a sequenced, severity-tagged list of maintenance steps ready for guided execution.

---

## Phase 05 — Guided Execution & Feedback Loop
**Tools:** Live Camera (WebRTC) · Text-to-Speech · Overshoot VLM · Canvas Overlay

### Purpose
This is where the maintenance actually happens. Phase 05 takes the Phase 04 subtask checklist and walks the user through it in real time. Audio instructions tell the user what to do. The live camera feed is continuously analyzed by Overshoot, which draws bounding boxes directly over the relevant machine components in view. After each action, Overshoot confirms whether the step is complete — if not, it loops, updating overlays and prompts until it is. The user never has to look away from the machine.

### Tasks

**5a · Live Camera Stream Capture**  
Access the user's device camera via WebRTC. Stream frames continuously to the inference pipeline for real-time visual analysis. Frames are sampled at a cadence sufficient for responsive feedback without overloading the inference layer.

**5b · Audio Prompt Delivery**  
Synthesize and play step-by-step audio instructions for the current subtask using TTS. Instructions are derived from the Phase 04 checklist and phrased in plain, actionable language so the user can keep their eyes and hands on the machine.

- Example prompt: *"Locate the oil drain plug on the lower-left panel. Unscrew it counterclockwise and place the drain pan beneath the opening."*

**5c · Overshoot Frame Inference**  
Send live camera frames to Overshoot with the active subtask as context. Query: *"Has this step been completed? Which components are relevant to this step right now?"* Overshoot returns component locations and a completion assessment.

**5d · Bounding Box Overlay Rendering**  
Draw real-time bounding boxes over components identified by Overshoot as relevant to the current subtask. Overlay colour coding:

| Colour | Meaning |
|---|---|
| 🟢 Green | Component correctly addressed |
| 🟡 Amber | Component relevant but not yet actioned |
| 🔴 Red | Problem detected or incorrect state |

**5e · Completion Detection & Loop Control**  
After each inference pass, evaluate whether Overshoot confirms the subtask is complete. If confirmed, advance to the next subtask and trigger the next audio prompt. If not confirmed, re-run inference, update overlays, and adjust the audio prompt to reflect what remains. Loop until completion is confirmed.

```
┌─────────────────────────────────┐
│      Load next subtask          │
└────────────┬────────────────────┘
             │
             ▼
      Play audio prompt
             │
             ▼
   Capture live camera frame
             │
             ▼
   Overshoot VLM inference
             │
             ▼
   Draw bounding box overlays
             │
        Confirmed?
        /        \
      Yes         No
       │           │
       ▼           └──► Update prompt & overlays
  Advance to              └──► Re-run inference
  next subtask
```

**5f · Session Summary & Sign-off**  
Once all subtasks are confirmed complete, generate a session log containing: completion timestamps per step, camera frames captured at moment of confirmation, any anomalies or low-confidence detections flagged during execution, and total session duration.

### Output
> **Verified Session Completion Log** — a timestamped, camera-evidenced record of every completed maintenance step with anomaly flags and sign-off data.

---

## Technology Stack

| Phase | Component | Tool |
|---|---|---|
| 01 | Web intelligence gathering | Browserbase |
| 02 | Visual machine state detection | Overshoot VLM |
| 03 | Manual and guide parsing | Document parser + LLM |
| 04 | Maintenance plan generation | LLM synthesis layer |
| 05 | Audio guidance | Text-to-Speech (TTS) |
| 05 | Live visual capture | WebRTC camera stream |
| 05 | Real-time component detection | Overshoot VLM |
| 05 | Overlay rendering | Canvas / AR layer |

---

## Key Design Principles

**Hands-free by default.** Audio prompts and visual overlays mean the user never needs to consult a screen or manual mid-task. Their hands and eyes stay on the machine.

**Guide-grounded.** Every subtask traces back to a step in the user's own machine guide. The system never invents procedures — it executes what the manual says, informed by what the camera sees.

**Closed-loop verification.** No step advances until Overshoot confirms it is complete. This prevents users from skipping steps or misidentifying completion.

**Machine-agnostic.** The pipeline is not built for a specific machine type. Any machine with a model identifier and an associated user guide can be processed.

**Traceable and auditable.** Every session produces a log with camera evidence. Maintenance records can be exported for compliance, warranty, or service history purposes.

---

*Machine Maintenance Assistant — Pipeline Spec v1.0*
