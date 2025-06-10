from __future__ import annotations

from typing import Any, get_args, get_origin, Union
from types import NotImplementedType, UnionType

import msgspec

from .types import CrockfordUUID
from .exceptions import CrockfordUUIDError


def cuuid_decoder(type_hint: Any, obj: Any) -> CrockfordUUID | NotImplementedType:
    """Decode CrockfordUUID strings for msgspec."""
    origin = get_origin(type_hint)
    args = get_args(type_hint)
    is_crockford_type = type_hint is CrockfordUUID or (
        origin in (Union, UnionType) and CrockfordUUID in args
    )

    if is_crockford_type:
        if obj is None:
            return NotImplemented
        if isinstance(obj, str):
            try:
                return CrockfordUUID(obj)
            except CrockfordUUIDError as exc:
                raise msgspec.ValidationError(str(exc)) from exc
        raise msgspec.ValidationError(
            f"Expected str for CrockfordUUID, got {type(obj).__name__}"
        )
    return NotImplemented


def cuuid_encoder(obj: Any) -> str | NotImplementedType:
    """Encode CrockfordUUID instances for msgspec."""
    return str(obj) if isinstance(obj, CrockfordUUID) else NotImplemented
