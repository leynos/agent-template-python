# pyright: reportMissingImports=false, reportAttributeAccessIssue=false
import importlib
import uuid

bindings = importlib.import_module(f"_{{ package_name }}_rs")
encode_crockford = bindings.encode_crockford  # type: ignore[attr-defined]
decode_crockford = bindings.decode_crockford  # type: ignore[attr-defined]
CrockfordUUID = bindings.CrockfordUUID  # type: ignore[attr-defined]


def test_round_trip() -> None:
    raw = bytes(range(16))
    encoded = encode_crockford(raw)
    decoded = decode_crockford(encoded)
    assert decoded == raw


def test_crockforduuid_construction_and_equality() -> None:
    raw = bytes(range(16))
    uuid_obj = uuid.UUID(bytes=raw)

    by_str = CrockfordUUID(encode_crockford(raw))
    by_bytes = CrockfordUUID(raw)
    by_uuid = CrockfordUUID(uuid_obj)

    assert by_str.bytes == raw
    assert by_bytes.bytes == raw
    assert by_uuid.bytes == raw
    assert by_str == by_bytes == by_uuid
    assert isinstance(by_uuid.uuid, uuid.UUID)


def test_case_insensitive_decoding() -> None:
    raw = bytes(range(16))
    encoded = encode_crockford(raw).lower()
    assert decode_crockford(encoded) == raw


def test_dunder_bytes() -> None:
    raw = bytes(range(16))
    cuuid = CrockfordUUID(raw)
    assert bytes(cuuid) == raw
