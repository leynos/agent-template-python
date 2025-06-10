# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportArgumentType=false
from __future__ import annotations

import importlib
import msgspec
import pytest

package = importlib.import_module("{{ package_name }}")
CrockfordUUID = package.CrockfordUUID
cuuid_decoder = package.cuuid_decoder
cuuid_encoder = package.cuuid_encoder


def test_encode_decode_round_trip() -> None:
    original = CrockfordUUID.generate_v4()
    encoded = cuuid_encoder(original)
    decoded = cuuid_decoder(CrockfordUUID, encoded)
    assert decoded == original


def test_invalid_decode_raises() -> None:
    with pytest.raises(msgspec.ValidationError):
        cuuid_decoder(CrockfordUUID, "not-a-cuuid")


def test_invalid_obj_type_raises() -> None:
    with pytest.raises(msgspec.ValidationError):
        cuuid_decoder(CrockfordUUID, 123)


def test_hooks_return_not_implemented() -> None:
    assert cuuid_decoder(str, "abc") is NotImplemented
    assert cuuid_encoder("abc") is NotImplemented


def test_decoder_optional_handling() -> None:
    hint = CrockfordUUID | None
    uuid_obj = CrockfordUUID.generate_v4()
    assert cuuid_decoder(hint, None) is NotImplemented
    assert cuuid_decoder(hint, str(uuid_obj)) == uuid_obj
