"""Reviewer findings classifier (P12-004).

Classifies a reviewer's free-text findings note into per-finding (text, severity)
pairs using a cheap LLM call. Falls back to an all-advisory result on any error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name
from core.engine.owned_helper_llm import run_owned_helper_completion

_SEVERITIES = ("critical", "notable", "advisory")
_PROMOTE_THRESHOLD = "notable"  # notable + critical → open_risks

_CLASSIFY_PROMPT_TEMPLATE = """\
You are reviewing a code-reviewer's findings note. Split it into individual findings \
and classify each as: critical (broken interface, data loss risk, security hole), \
notable (missing error handling, test gap, unclear contract), advisory (style, minor \
refactor suggestion, non-blocking).

Respond ONLY with a JSON array, no prose:
[{{"text": "...", "severity": "critical|notable|advisory"}}, ...]

Reviewer note:
{note}

{spec_block}\
"""


@dataclass
class ClassifiedFinding:
    text: str
    severity: str  # "advisory" | "notable" | "critical"


def classify_reviewer_findings(
    note: str,
    *,
    spec_contract: str | None = None,
    workspace_path: str,
    delegation_id: str,
) -> list[ClassifiedFinding]:
    """Split and classify reviewer findings note into (text, severity) pairs.

    Uses a cheap LLM call (ROLE_SUPERVISOR model, no tool-calling loop).
    Falls back to all-advisory if the LLM call fails or model is misconfigured.
    Returns [] if note is empty. Never raises.
    """
    note = (note or "").strip()
    if not note:
        return []

    spec_block = (
        f"Spec contract (for calibration):\n{spec_contract[:400]}"
        if spec_contract
        else ""
    )
    prompt = _CLASSIFY_PROMPT_TEMPLATE.format(
        note=note[:1500],
        spec_block=spec_block,
    )

    try:
        apply_provider_env()
        model = resolve_role_model_name(ROLE_SUPERVISOR, workspace_path)
        if provider_hint_for_model(model):
            return _fallback(note)

        completion = run_owned_helper_completion(
            [{"role": "user", "content": prompt}],
            model=model,
        )
        if completion.error or not completion.text:
            return _fallback(note)

        return _parse_findings(completion.text, note)

    except Exception:
        return _fallback(note)


def _fallback(note: str) -> list[ClassifiedFinding]:
    return [ClassifiedFinding(text=note, severity="advisory")]


def _parse_findings(text: str, note: str) -> list[ClassifiedFinding]:
    """Extract JSON array from LLM response; fall back to advisory on any parse error."""
    try:
        import json

        m = re.search(r"\[.*\]", text, re.DOTALL)
        if m is None:
            return _fallback(note)
        raw = json.loads(m.group(0))
        if not isinstance(raw, list):
            return _fallback(note)
        findings: list[ClassifiedFinding] = []
        for item in raw[:10]:
            if not isinstance(item, dict):
                continue
            item_text = str(item.get("text") or "").strip()
            if not item_text:
                continue
            severity = str(item.get("severity") or "advisory").lower()
            if severity not in _SEVERITIES:
                severity = "advisory"
            findings.append(ClassifiedFinding(text=item_text, severity=severity))
        return findings if findings else _fallback(note)
    except Exception:
        return _fallback(note)
