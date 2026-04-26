"""Lightweight PII masking for HIPAA / GDPR-friendly logging.

This is intentionally rule-based and dependency-free so the system works
offline and deterministically in CI. Production deployments should layer
this with a vetted de-identification service (e.g. presidio).
"""

from __future__ import annotations

import re

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"\b(?:\+?\d{1,2}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("MRN", re.compile(r"\bMRN[:#-]?\s?\d{4,}\b", re.IGNORECASE)),
    ("DOB", re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")),
    ("DATE", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    # Conservative name pattern: two capitalized words; we apply it last and
    # only when explicitly requested via ``aggressive=True``.
]

_NAME_PATTERN = re.compile(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b")


def mask(text: str, aggressive: bool = False) -> str:
    """Mask PII in *text*.

    Replaces emails, phones, SSNs, MRN labels, and dates with ``[REDACTED:<TYPE>]``.
    When ``aggressive`` is true, also masks two-word capitalized sequences as names.
    """
    if not text:
        return text
    out = text
    for tag, pattern in _PII_PATTERNS:
        out = pattern.sub(f"[REDACTED:{tag}]", out)
    if aggressive:
        out = _NAME_PATTERN.sub("[REDACTED:NAME]", out)
    return out


def mask_dict(data: dict, aggressive: bool = False) -> dict:
    """Recursively mask string values in a JSON-like dict."""
    out: dict = {}
    for k, v in data.items():
        if isinstance(v, str):
            out[k] = mask(v, aggressive=aggressive)
        elif isinstance(v, dict):
            out[k] = mask_dict(v, aggressive=aggressive)
        elif isinstance(v, list):
            out[k] = [mask_dict(x, aggressive) if isinstance(x, dict) else (mask(x, aggressive) if isinstance(x, str) else x) for x in v]
        else:
            out[k] = v
    return out
