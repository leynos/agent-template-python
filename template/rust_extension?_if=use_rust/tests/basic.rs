use _{{ package_name }}_rs::{decode_crockford_to_bytes, encode_bytes_to_crockford};

#[test]
fn round_trip() {
    let bytes = [1u8; 16];
    let encoded = encode_bytes_to_crockford(&bytes);
    let decoded = decode_crockford_to_bytes(&encoded).unwrap();
    assert_eq!(bytes, decoded);
}
