"""Markdown section helpers for workspace task specs."""

from __future__ import annotations

import re
from typing import Any

import yaml

PLANNER_SECTION_TITLES = (
    "Goal",
    "Scope",
    "Files",
    "Constraints",
    "Done when",
    "Plan",
)

EPIC_SECTION_TITLES = (
    "Goal",
    "Steps",
    "Out of scope",
)

MCP_OWNED_SECTION_TITLES = (
    "Status",
    "Run log",
    "Scope expansion",
    "Worker feedback",
    "Blockers / questions",
    "Suggested next (hints only)",
)

# Report status — planner marks task spec done after verification.
REPORT_STATUS_DELEGATED_OK = "delegated_ok"
REPORT_STATUS_BLOCKED = "blocked"
REPORT_STATUS_OPEN = "open"
REPORT_STATUS_REVIEWED = "reviewed"

FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SECTION_HEADER_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """YAML front matter between --- markers; returns ({}, body) if absent or invalid."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml = match.group(1)
    body = text[match.end() :]
    if not raw_yaml.strip():
        return {}, body
    try:
        data = yaml.safe_load(raw_yaml)
    except yaml.YAMLError:
        return {}, body
    if data is None:
        return {}, body
    if not isinstance(data, dict):
        return {}, body
    return data, body


def join_front_matter(data: dict[str, Any], body: str) -> str:
    if not data:
        return body
    lines = ["---"]
    for key, value in data.items():
        if value is None or value == "":
            lines.append(f'{key}: ""')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.lstrip("\n")


def parse_sections(body: str) -> dict[str, str]:
    """Map ## Section title → content (until next ## or EOF)."""
    sections: dict[str, str] = {}
    matches = list(SECTION_HEADER_RE.finditer(body))
    for idx, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        sections[title] = body[start:end].strip()
    return sections


def replace_section_body(body: str, title: str, new_content: str) -> str:
    """Replace one ## section body; append section if missing."""
    pattern = re.compile(
        rf"(^## {re.escape(title)}\s*\n)(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    replacement = rf"\1{new_content.rstrip()}\n\n"
    if pattern.search(body):
        return pattern.sub(replacement, body, count=1)
    return body.rstrip() + f"\n\n## {title}\n\n{new_content.rstrip()}\n"
