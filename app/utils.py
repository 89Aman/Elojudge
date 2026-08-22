"""Shared utility functions for EloJudge."""

from __future__ import annotations

import re


def extract_json(text: str) -> str:
    """Extract outermost JSON object from text, stripping markdown fences."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text
