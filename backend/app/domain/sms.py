"""SMS segment math: GSM-7 vs Unicode (UCS-2) encodings."""

# GSM-7 basic alphabet plus extension-table chars (extension chars cost 2 septets).
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = "^{}\\[~]|€"

GSM7_SINGLE_SEPTETS = 160
GSM7_CONCAT_SEPTETS = 153
UCS2_SINGLE_UNITS = 70
UCS2_CONCAT_UNITS = 67


def is_gsm7(text: str) -> bool:
    allowed = set(GSM7_BASIC) | set(GSM7_EXTENDED)
    return all(c in allowed for c in text)


def _gsm7_units(text: str) -> int:
    extended = set(GSM7_EXTENDED)
    return sum(2 if c in extended else 1 for c in text)


def _ucs2_units(text: str) -> int:
    # Astral characters (emoji etc.) take a surrogate pair.
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


def sms_segments(text: str) -> int:
    """Number of SMS segments the text needs (1 target, 2 last resort)."""
    if is_gsm7(text):
        units = _gsm7_units(text)
        if units <= GSM7_SINGLE_SEPTETS:
            return 1
        return (units + GSM7_CONCAT_SEPTETS - 1) // GSM7_CONCAT_SEPTETS
    units = _ucs2_units(text)
    if units <= UCS2_SINGLE_UNITS:
        return 1
    return (units + UCS2_CONCAT_UNITS - 1) // UCS2_CONCAT_UNITS
