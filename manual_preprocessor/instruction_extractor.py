"""Extract structured repair instructions from parsed pages."""

from __future__ import annotations

import re
from typing import Optional

from .models import InstructionStep, ParsedPage

# Common repair action verbs
_ACTION_VERBS: dict[str, list[str]] = {
    "remove": ["remove", "detach", "pull out", "take off", "unscrew", "disconnect", "extract"],
    "install": ["install", "attach", "insert", "mount", "connect", "plug in", "screw in"],
    "rotate": ["rotate", "turn", "twist", "spin", "dial"],
    "press": ["press", "push", "click", "depress", "hold down"],
    "align": ["align", "position", "center", "orient", "place"],
    "tighten": ["tighten", "torque", "secure", "fasten"],
    "loosen": ["loosen", "unfasten", "release"],
    "clean": ["clean", "wipe", "rinse", "flush", "wash"],
    "inspect": ["inspect", "check", "verify", "examine", "look at", "confirm"],
    "measure": ["measure", "gauge", "test"],
    "apply": ["apply", "spread", "coat", "lubricate", "grease"],
    "cut": ["cut", "trim", "snip", "slice"],
    "open": ["open", "lift", "raise", "unlock", "pry"],
    "close": ["close", "shut", "lower", "lock", "seal"],
    "replace": ["replace", "swap", "substitute", "change"],
    "adjust": ["adjust", "set", "calibrate", "tune"],
}

# Flatten for fast lookup: phrase -> canonical action
_PHRASE_TO_ACTION: dict[str, str] = {}
for action, phrases in _ACTION_VERBS.items():
    for phrase in phrases:
        _PHRASE_TO_ACTION[phrase] = action

# Common tool words
_TOOL_KEYWORDS = {
    "screwdriver", "wrench", "pliers", "hammer", "drill", "socket",
    "hex key", "allen key", "torx", "multimeter", "soldering iron",
    "knife", "scissors", "pry tool", "spudger", "tweezers",
    "ratchet", "clamp", "vice", "file", "sandpaper",
}


# ------------------------------------------------------------------
# Step segmentation
# ------------------------------------------------------------------


def segment_steps(parsed_pages: list[ParsedPage]) -> list[tuple[str, int]]:
    """Split page text into individual instruction step strings.

    Returns (step_text, page_number) tuples.
    """
    steps: list[tuple[str, int]] = []

    for page in parsed_pages:
        full_text = " ".join(tb.text for tb in page.text_blocks)
        page_steps = _split_into_steps(full_text)
        for s in page_steps:
            steps.append((s, page.page_number))

    return steps


def _split_into_steps(text: str) -> list[str]:
    """Detect numbered lists and imperative sentences."""
    # Try numbered list first: "1. Do X  2. Do Y" or "1) Do X"
    numbered = re.split(r"(?:^|\n)\s*\d+[\.\)]\s*", text)
    numbered = [s.strip() for s in numbered if s.strip()]
    if len(numbered) > 1:
        return numbered

    # Try bullet points
    bulleted = re.split(r"(?:^|\n)\s*[\-\*\u2022]\s*", text)
    bulleted = [s.strip() for s in bulleted if s.strip()]
    if len(bulleted) > 1:
        return bulleted

    # Fall back to sentence splitting, keeping only imperative sentences
    sentences = re.split(r"(?<=[.!])\s+", text)
    steps: list[str] = []
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        # Keep sentences that start with a verb (imperative) or contain action words
        first_word = sent.split()[0].lower() if sent.split() else ""
        if first_word in _PHRASE_TO_ACTION or _contains_action(sent):
            steps.append(sent)

    return steps if steps else [text.strip()] if text.strip() else []


def _contains_action(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _PHRASE_TO_ACTION)


# ------------------------------------------------------------------
# Command extraction
# ------------------------------------------------------------------


def extract_commands(
    step_text: str,
    step_id: int = 0,
    page_reference: int | None = None,
) -> InstructionStep:
    """Parse a step string into a structured InstructionStep."""
    action = _extract_action(step_text)
    target = _extract_target(step_text, action)
    tool = _extract_tool(step_text)
    params = _extract_parameters(step_text, action, target)

    return InstructionStep(
        step_id=step_id,
        raw_text=step_text,
        action=action,
        target_object=target,
        tool=tool,
        parameters=params,
        page_reference=page_reference,
    )


def _extract_action(text: str) -> str:
    lower = text.lower()
    # Try multi-word phrases first (longer matches win)
    for phrase in sorted(_PHRASE_TO_ACTION, key=len, reverse=True):
        if phrase in lower:
            return _PHRASE_TO_ACTION[phrase]
    return "perform"  # fallback


def _extract_target(text: str, action: str) -> str:
    """Extract the object being acted upon.

    Simple heuristic: take the noun phrase after the action verb.
    """
    lower = text.lower()
    # Find the action verb phrase in text
    for phrase in sorted(_PHRASE_TO_ACTION, key=len, reverse=True):
        if _PHRASE_TO_ACTION.get(phrase) == action and phrase in lower:
            idx = lower.index(phrase) + len(phrase)
            remainder = text[idx:].strip().strip(".")
            # Take words until a preposition or conjunction
            words = remainder.split()
            target_words: list[str] = []
            stop_words = {"to", "from", "with", "using", "into", "onto", "until", "by", "at", "and", "then"}
            for w in words:
                if w.lower() in stop_words:
                    break
                # Skip articles
                if w.lower() in {"the", "a", "an"}:
                    continue
                target_words.append(w)
                if len(target_words) >= 4:
                    break
            if target_words:
                return " ".join(target_words).strip(".,;:")
            break

    return "component"


def _extract_tool(text: str) -> Optional[str]:
    lower = text.lower()
    for tool in sorted(_TOOL_KEYWORDS, key=len, reverse=True):
        if tool in lower:
            return tool
    # Check for "using <tool>" pattern
    m = re.search(r"(?:using|with)\s+(?:a\s+)?(\w[\w\s]{0,20})", lower)
    if m:
        candidate = m.group(1).strip()
        if len(candidate) > 2:
            return candidate
    return None


def _extract_parameters(text: str, action: str, target: str) -> Optional[str]:
    """Extract parameters like positions, values, directions."""
    lower = text.lower()
    # Look for "to <value>" patterns
    m = re.search(r"\bto\s+(position\s+\w+|\d+[\w°]*|the\s+\w+\s+position)", lower)
    if m:
        return m.group(1)
    # Look for measurement values
    m = re.search(r"(\d+\.?\d*\s*(?:mm|cm|inch|in|ft|nm|°|degrees|turns?))", lower)
    if m:
        return m.group(1)
    # Look for "until <condition>"
    m = re.search(r"until\s+(.+?)(?:\.|$)", lower)
    if m:
        return m.group(1).strip()
    return None


# ------------------------------------------------------------------
# High-level: pages -> InstructionSteps
# ------------------------------------------------------------------


def extract_all_instructions(parsed_pages: list[ParsedPage]) -> list[InstructionStep]:
    """Full extraction pipeline: segment then extract commands."""
    raw_steps = segment_steps(parsed_pages)
    instructions: list[InstructionStep] = []

    for idx, (step_text, page_num) in enumerate(raw_steps):
        step = extract_commands(step_text, step_id=idx + 1, page_reference=page_num)
        instructions.append(step)

    return instructions
