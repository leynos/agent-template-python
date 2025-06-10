# pyright: reportMissingImports=false, reportGeneralTypeIssues=false, reportArgumentType=false
from __future__ import annotations

import importlib
import uuid
import pytest

package = importlib.import_module("{{ package_name }}")
CrockfordUUID = package.CrockfordUUID


def test_str_round_trip() -> None:
    cuuid = CrockfordUUID.generate_v4()
    assert CrockfordUUID(str(cuuid)) == cuuid


def test_uuid_property_returns_uuid() -> None:
    cuuid = CrockfordUUID.generate_v4()
    assert isinstance(cuuid.uuid, uuid.UUID)
    assert cuuid.uuid.bytes == cuuid.bytes


def test_invalid_bytes_length() -> None:
    with pytest.raises(ValueError):
        CrockfordUUID(b"short")


def test_invalid_string_input() -> None:
    with pytest.raises(ValueError):
        CrockfordUUID("invalid")


def test_invalid_type_input() -> None:
    with pytest.raises(ValueError):
        CrockfordUUID(123)  # type: ignore[arg-type]


def test_generate_v7_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(uuid, "uuid7", raising=False)
    with pytest.raises(NotImplementedError):
        CrockfordUUID.generate_v7()
