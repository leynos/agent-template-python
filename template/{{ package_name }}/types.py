from __future__ import annotations

from typing import ClassVar
import uuid

from .exceptions import CrockfordUUIDError
from .pure import decode_crockford, encode_crockford


class CrockfordUUID(uuid.UUID):
    """UUID stored as Crockford Base32 when stringified."""

    _expected_length: ClassVar[int] = 16

    def __new__(cls, value: str | bytes | uuid.UUID) -> "CrockfordUUID":
        if isinstance(value, uuid.UUID):
            bytes_value = value.bytes
        elif isinstance(value, (bytes, bytearray)):
            if len(value) != cls._expected_length:
                raise CrockfordUUIDError(
                    f"expected {cls._expected_length} bytes, got {len(value)}"
                )
            bytes_value = bytes(value)
        elif isinstance(value, str):
            try:
                bytes_value = decode_crockford(value)
            except ValueError as exc:
                raise CrockfordUUIDError(str(exc)) from exc
        else:
            raise CrockfordUUIDError(
                "expected Crockford string, 16 bytes, or uuid.UUID"
            )
        obj = object.__new__(cls)
        uuid.UUID.__init__(obj, bytes=bytes_value)
        return obj

    def __init__(self, value: str | bytes | uuid.UUID) -> None:
        pass

    @classmethod
    def generate_v4(cls) -> "CrockfordUUID":
        return cls(uuid.uuid4())

    @classmethod
    def generate_v7(cls) -> "CrockfordUUID":
        if not hasattr(uuid, "uuid7"):
            raise NotImplementedError("uuid.uuid7 is not available")
        return cls(uuid.uuid7())  # pyright: ignore[reportAttributeAccessIssue]

    @property
    def uuid(self) -> uuid.UUID:
        """Return a `uuid.UUID` instance representing this CrockfordUUID."""
        return uuid.UUID(bytes=self.bytes)

    def __str__(self) -> str:
        return encode_crockford(self.bytes)

    def __repr__(self) -> str:
        return f"CrockfordUUID('{self}')"
