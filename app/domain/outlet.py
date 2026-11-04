"""Broadcaster-pack validators: radio timing/readability, SMS length policy."""

import re

from app.domain.sms import sms_segments

RADIO_MIN_WORDS = 65
RADIO_MAX_WORDS = 75
SMS_MAX_SEGMENTS = 2

_ABBREV_RE = re.compile(r"\b[A-Z]{2,}\b")
_DIGIT_RE = re.compile(r"[0-9]")


def word_count(text: str) -> int:
    return len(text.split())


def validate_radio_script(script: str) -> list[str]:
    """65-75 spoken words, no abbreviations, no digits (spell numbers out)."""
    errors = []
    words = word_count(script)
    if not RADIO_MIN_WORDS <= words <= RADIO_MAX_WORDS:
        errors.append(f"radio script has {words} words, need 65-75")
    abbrevs = sorted(set(_ABBREV_RE.findall(script)))
    if abbrevs:
        errors.append(f"abbreviations not allowed: {', '.join(abbrevs[:5])}")
    if _DIGIT_RE.search(script):
        errors.append("digits not allowed: spell numbers as words")
    return errors


def validate_sms(text: str) -> list[str]:
    """SMS must fit in 2 segments (1 segment is the generation target)."""
    errors = []
    if not text.strip():
        errors.append("sms is empty")
        return errors
    segments = sms_segments(text)
    if segments > SMS_MAX_SEGMENTS:
        errors.append(f"sms needs {segments} segments, max is {SMS_MAX_SEGMENTS}")
    return errors
