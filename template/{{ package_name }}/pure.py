from __future__ import annotations

import base64

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_STANDARD_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
_ENCODE_TRANS = str.maketrans(_STANDARD_ALPHABET, _ALPHABET)
_DECODE_TRANS = str.maketrans(
    {
        "i": "1",
        "I": "1",
        "l": "1",
        "L": "1",
        "o": "0",
        "O": "0",
        "-": "",
    }
)
_REVERSE_TRANS = str.maketrans(_ALPHABET, _STANDARD_ALPHABET)


def encode_crockford(b: bytes) -> str:
    """Encode 16 bytes into a Crockford Base32 string."""
    if len(b) != 16:
        raise ValueError(f"expected 16 bytes, got {len(b)}")
    encoded = base64.b32encode(b).decode("ascii").rstrip("=")
    return encoded.translate(_ENCODE_TRANS)


def decode_crockford(s: str) -> bytes:
    """Decode a Crockford Base32 string into bytes."""
    clean = s.translate(_DECODE_TRANS).upper()
    if len(clean) != 26:
        raise ValueError(f"expected 26 characters, got {len(clean)}")
    standard = clean.translate(_REVERSE_TRANS)
    padding = "=" * ((8 - len(standard) % 8) % 8)
    out = base64.b32decode(standard + padding, casefold=True)
    if len(out) != 16:
        raise ValueError(f"expected 16 bytes, got {len(out)}")
    return out
