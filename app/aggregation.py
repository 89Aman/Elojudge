"""Severity and keyword aggregation for feedback clusters."""

from __future__ import annotations

import re

CRITICAL_KEYWORDS = {
    "crash", "crashes", "crashing", "crashed",
    "data loss", "dataloss", "security", "vulnerability", "vulnerabilities",
    "leak", "leaking", "leaks", "corrupt", "corruption", "corrupted",
    "outage", "outages", "exploit", "exploits",
}

HIGH_KEYWORDS = {
    "broken", "broke", "cannot", "cant", "can't", "freeze", "freezes",
    "freezing", "frozen", "hang", "hangs", "hanging", "blocked",
    "fail", "fails", "failing", "failed", "failure", "error", "errors",
    "sync", "syncing", "lost", "unusable", "critical", "urgent",
}

MEDIUM_KEYWORDS = {
    "search", "searching", "filter", "filters", "filtering",
    "export", "exporting", "exports", "import", "importing",
    "organize", "organization", "organizing", "folder", "folders",
    "tag", "tags", "tagging", "backup", "offline", "performance",
    "slow", "speed", "integrate", "integration", "api", "share",
    "sharing", "voice", "template", "templates", "pdf",
}

LOW_KEYWORDS = {
    "dark mode", "darkmode", "theme", "themes", "color", "colors",
    "icon", "icons", "font", "fonts", "animation", "animations",
    "button size", "spacing", "cosmetic", "look", "ui design",
}


def extract_keywords(text: str, keyword_set: set[str]) -> list[str]:
    """Find all matching keywords from a set in the text."""
    lowered = text.lower()
    matches = []
    for kw in keyword_set:
        if " " in kw:
            if kw in lowered:
                matches.append(kw)
        else:
            if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
                matches.append(kw)
    return matches


def determine_severity(text: str) -> str:
    """Classify cluster severity: critical, high, medium, or low."""
    lowered = text.lower()

    if extract_keywords(lowered, CRITICAL_KEYWORDS):
        return "critical"
    if extract_keywords(lowered, HIGH_KEYWORDS):
        return "high"
    if extract_keywords(lowered, MEDIUM_KEYWORDS):
        return "medium"
    if extract_keywords(lowered, LOW_KEYWORDS):
        return "low"

    return "medium"


def get_severity_weight(severity: str) -> float:
    """Return numeric weight for severity level."""
    weights = {
        "critical": 3.0,
        "high": 2.0,
        "medium": 1.0,
        "low": 0.3,
    }
    return weights.get(severity.lower(), 1.0)
