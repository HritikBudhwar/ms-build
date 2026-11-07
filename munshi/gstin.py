"""GSTIN structure and checksum validation (the same mod-36 scheme the GST portal uses)."""

import re

_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

STATE_CODES = {
    "27": "Maharashtra",
    "29": "Karnataka",
    "33": "Tamil Nadu",
    "36": "Telangana",
    "32": "Kerala",
    "24": "Gujarat",
    "07": "Delhi",
}


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        product = _CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _CHARS[(36 - total % 36) % 36]


def with_checksum(first14: str) -> str:
    return first14 + checksum_char(first14)


def validate(gstin: str) -> tuple[bool, str]:
    """Return (ok, reason). Reason is empty when ok."""
    g = (gstin or "").strip().upper()
    if not _PATTERN.match(g):
        return False, "GSTIN does not match the 15-character format"
    if g[:2] not in STATE_CODES:
        return False, f"Unknown state code {g[:2]}"
    if checksum_char(g[:14]) != g[14]:
        return False, f"Checksum digit is {g[14]}, expected {checksum_char(g[:14])}"
    return True, ""


def state_of(gstin: str) -> str:
    return STATE_CODES.get(gstin[:2], "Unknown")
