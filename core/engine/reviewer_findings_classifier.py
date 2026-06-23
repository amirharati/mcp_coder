"""Reviewer findings classifier (P12-004).

Classifies a reviewer's free-text findings note into per-finding (text, severity)
pairs using a cheap LLM call. Falls back to an all-advisory result on any error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from core.config.models import provider_hint_for_model
from core.config.providers import apply_provider_env
from core.config.role_models import ROLE_SUPERVISOR, resolve_role_model_name
from core.engine.owned_helper_llm import run_owned_helper_completion

_SEVERITIES = ("critical", "notable", "advisory")
_PROMOTE_THRESHOLD = "notable"  # notable + critical → open_risks
_PROMOTED_SEVERITIES = ("notable", "critical")

_STRONG_ABSENCE_RE = re.compile(
    r"\b(?:not\s+present|does\s+not\s+exist|doesn't\s+exist|do\s+not\s+exist|"
    r"don't\s+exist|is\s+absent|are\s+absent)\b",
    re.IGNORECASE,
)
_MISSING_SYMBOL_RE = re.compile(
    r"\bmissing\s+(?:the\s+)?(?:(?:class|dataclass|model|symbol|entity)\s+)?"
    r"`?([A-Za-z_][A-Za-z0-9_]*)`?",
    re.IGNORECASE,
)
_BACKTICK_SYMBOL_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
_CLASSLIKE_SYMBOL_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")
_IGNORED_CLASSLIKE_WORDS = frozenset(
    {
        "A",
        "An",
        "And",
        "But",
        "Does",
        "Missing",
        "No",
        "Not",
        "The",
        "This",
    }
)

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


def should_promote_finding_to_risk(
    finding: ClassifiedFinding,
    *,
    changed_file_contents: Mapping[str, str] | None = None,
) -> bool:
    """Return whether a classified reviewer finding should become an open risk."""
    if finding.severity not in _PROMOTED_SEVERITIES:
        return False
    if finding_absence_claim_contradicted(
        finding.text,
        changed_file_contents=changed_file_contents or {},
    ):
        return False
    return True


def finding_absence_claim_contradicted(
    finding_text: str,
    *,
    changed_file_contents: Mapping[str, str],
) -> bool:
    """Detect obvious reviewer false positives about missing symbols."""
    symbols = _extract_absence_claim_symbols(finding_text)
    if not symbols or not changed_file_contents:
        return False

    for symbol in symbols:
        if any(
            _content_declares_symbol(content, symbol)
            for content in changed_file_contents.values()
        ):
            return True
    return False


def _extract_absence_claim_symbols(finding_text: str) -> set[str]:
    text = (finding_text or "").strip()
    if not text:
        return set()

    symbols: set[str] = set()
    if _STRONG_ABSENCE_RE.search(text):
        symbols.update(_BACKTICK_SYMBOL_RE.findall(text))
        symbols.update(
            token
            for token in _CLASSLIKE_SYMBOL_RE.findall(text)
            if token not in _IGNORED_CLASSLIKE_WORDS
        )

    for match in _MISSING_SYMBOL_RE.finditer(text):
        symbol = match.group(1)
        if symbol[:1].isupper() or f"`{symbol}`" in match.group(0):
            symbols.add(symbol)

    return symbols


def _content_declares_symbol(content: str, symbol: str) -> bool:
    if not symbol or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", symbol):
        return False

    escaped = re.escape(symbol)
    declaration_patterns = (
        rf"\bclass\s+{escaped}\b",
        rf"\b(?:async\s+)?def\s+{escaped}\b",
        rf"\b{escaped}\s*=",
        rf"\b{escaped}\s*:",
    )
    return any(re.search(pattern, content) for pattern in declaration_patterns)


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
