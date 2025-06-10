"""{{ project_name }} package."""

from __future__ import annotations

from .exceptions import CrockfordUUIDError
from .hooks import cuuid_decoder, cuuid_encoder

PACKAGE_NAME = "{{ package_name }}"

try:  # pragma: no cover - rust optional
    rust = __import__(f"_{PACKAGE_NAME}_rs")
    encode_crockford = rust.encode_crockford  # type: ignore[attr-defined]
    decode_crockford = rust.decode_crockford  # type: ignore[attr-defined]
    CrockfordUUID = rust.CrockfordUUID  # type: ignore[attr-defined]
except ModuleNotFoundError:
    from .pure import decode_crockford, encode_crockford
    from .types import CrockfordUUID

__all__ = [
    "CrockfordUUID",
    "decode_crockford",
    "encode_crockford",
    "CrockfordUUIDError",
    "cuuid_decoder",
    "cuuid_encoder",
]
