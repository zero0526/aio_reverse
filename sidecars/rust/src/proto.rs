//! Wire protocol v1 framing and descriptor hashing.

use std::io::{self, Read, Write};

use serde_json::Value;

pub const HEADER_BYTES: usize = 8;
pub const MAX_JSON_BYTES: usize = 64 * 1024 * 1024;
pub const MAX_BIN_BYTES: usize = 512 * 1024 * 1024;

const FNV_OFFSET_BASIS: u64 = 0xcbf2_9ce4_8422_2325;
const FNV_PRIME: u64 = 0x0000_0100_0000_01b3;

/// Reads one frame. Returns `Ok(None)` at a clean end of stream.
pub fn read_frame<R: Read>(reader: &mut R) -> io::Result<Option<(Value, Vec<u8>)>> {
    let mut header = [0u8; HEADER_BYTES];
    if let Err(err) = reader.read_exact(&mut header) {
        if err.kind() == io::ErrorKind::UnexpectedEof {
            return Ok(None);
        }
        return Err(err);
    }

    let json_len = u32::from_be_bytes(header[0..4].try_into().expect("4-byte slice")) as usize;
    let bin_len = u32::from_be_bytes(header[4..8].try_into().expect("4-byte slice")) as usize;
    if json_len > MAX_JSON_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("frame json length {json_len} exceeds the 64 MiB cap"),
        ));
    }
    if bin_len > MAX_BIN_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("frame binary length {bin_len} exceeds the 512 MiB cap"),
        ));
    }

    let mut json_bytes = vec![0u8; json_len];
    reader.read_exact(&mut json_bytes)?;
    let mut bin = vec![0u8; bin_len];
    reader.read_exact(&mut bin)?;

    let value: Value = serde_json::from_slice(&json_bytes).map_err(|err| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("frame JSON is invalid: {err}"),
        )
    })?;
    Ok(Some((value, bin)))
}

/// Writes one frame and flushes it.
pub fn write_frame<W: Write>(writer: &mut W, envelope: &Value, bin: &[u8]) -> io::Result<()> {
    let json = serde_json::to_vec(envelope).map_err(|err| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("failed to serialize envelope: {err}"),
        )
    })?;
    if json.len() > MAX_JSON_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("envelope json length {} exceeds the 64 MiB cap", json.len()),
        ));
    }
    if bin.len() > MAX_BIN_BYTES {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("frame binary length {} exceeds the 512 MiB cap", bin.len()),
        ));
    }

    let mut header = [0u8; HEADER_BYTES];
    header[0..4].copy_from_slice(&(json.len() as u32).to_be_bytes());
    header[4..8].copy_from_slice(&(bin.len() as u32).to_be_bytes());
    writer.write_all(&header)?;
    writer.write_all(&json)?;
    writer.write_all(bin)?;
    writer.flush()
}

/// Canonical JSON for `schema_hash`: `serde_json`'s default map is a
/// `BTreeMap`, so object keys are already sorted recursively; serialization is
/// compact and keeps UTF-8 unescaped.
pub fn canonical_json(value: &Value) -> Vec<u8> {
    serde_json::to_vec(value).expect("serde_json::Value always serializes")
}

/// FNV-1a 64-bit, formatted as 16 lowercase hex digits.
pub fn fnv1a64(data: &[u8]) -> String {
    let mut digest = FNV_OFFSET_BASIS;
    for byte in data {
        digest ^= u64::from(*byte);
        digest = digest.wrapping_mul(FNV_PRIME);
    }
    format!("{digest:016x}")
}

pub fn schema_hash(descriptor: &Value) -> String {
    fnv1a64(&canonical_json(descriptor))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn fnv1a64_matches_known_vectors() {
        assert_eq!(fnv1a64(b""), "cbf29ce484222325");
        assert_eq!(fnv1a64(b"a"), "af63dc4c8601ec8c");
        assert_eq!(fnv1a64(b"foobar"), "85944171f73967e8");
    }

    #[test]
    fn canonical_json_sorts_keys_recursively() {
        let value: Value = serde_json::from_str(r#"{"b":1,"a":{"d":2,"c":3}}"#).unwrap();
        assert_eq!(canonical_json(&value), br#"{"a":{"c":3,"d":2},"b":1}"#);
    }

    #[test]
    fn schema_hash_is_order_independent() {
        let left: Value = serde_json::from_str(r#"{"a":1,"b":[1,{"d":4,"c":3}]}"#).unwrap();
        let right: Value = serde_json::from_str(r#"{"b":[1,{"c":3,"d":4}],"a":1}"#).unwrap();
        assert_eq!(schema_hash(&left), schema_hash(&right));
    }

    #[test]
    fn frame_roundtrip_preserves_json_and_binary() {
        let envelope = serde_json::json!({"t": "req", "v": 1, "id": 7});
        let mut bytes = Vec::new();
        write_frame(&mut bytes, &envelope, b"\x00\x01\x02").unwrap();
        let (decoded, bin) = read_frame(&mut Cursor::new(bytes)).unwrap().unwrap();
        assert_eq!(decoded, envelope);
        assert_eq!(bin, b"\x00\x01\x02");
    }

    #[test]
    fn read_frame_reports_clean_eof() {
        let mut empty = Cursor::new(Vec::new());
        assert!(read_frame(&mut empty).unwrap().is_none());
    }
}
