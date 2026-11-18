import re

_UNITS = {"h": 3600, "m": 60, "s": 1}


def parse_duration(text):
    match = re.fullmatch(r"\s*(\d+)([hms])\s*", text)
    if not match:
        raise ValueError(f"invalid duration: {text!r}")
    amount, unit = match.groups()
    return int(amount) * _UNITS[unit]
