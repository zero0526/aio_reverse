//! Descriptor validation and bundle/handshake constants.

use std::collections::HashSet;

use serde_json::{json, Value};

use crate::error::{ErrorKind, SidecarError};

pub const PROTOCOL: u64 = 1;
pub const BUNDLE: &str = "aio";
pub const HOST_VERSION: &str = "0.1.0";

pub const BASE_OPS: [&str; 10] = [
    "hello",
    "describe",
    "targets",
    "metrics",
    "open",
    "close",
    "health",
    "warmup",
    "shutdown",
    "diag",
];

#[derive(Debug, Clone)]
pub struct OpSpec {
    pub name: String,
    pub deadline_ms: Option<u64>,
}

#[derive(Debug, Clone)]
pub struct Descriptor {
    pub value: Value,
    pub id: String,
    pub ops: Vec<OpSpec>,
}

impl Descriptor {
    pub fn parse(value: Value) -> Result<Self, SidecarError> {
        let object = value.as_object().ok_or_else(|| {
            SidecarError::new(
                ErrorKind::Internal,
                "engine.describe() must return a JSON object",
            )
        })?;

        let id = object
            .get("id")
            .and_then(Value::as_str)
            .filter(|id| !id.is_empty())
            .ok_or_else(|| {
                SidecarError::new(
                    ErrorKind::Internal,
                    "engine descriptor requires a non-empty string id",
                )
            })?
            .to_string();

        let raw_ops = object
            .get("ops")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                SidecarError::new(
                    ErrorKind::Internal,
                    format!("engine \"{id}\" descriptor requires an ops array"),
                )
            })?;

        let mut ops = Vec::with_capacity(raw_ops.len());
        let mut seen = HashSet::new();
        for raw_op in raw_ops {
            let name = raw_op
                .get("name")
                .and_then(Value::as_str)
                .filter(|name| !name.is_empty())
                .ok_or_else(|| {
                    SidecarError::new(
                        ErrorKind::Internal,
                        format!("engine \"{id}\" has an op without a name"),
                    )
                })?
                .to_string();
            if !seen.insert(name.clone()) {
                return Err(SidecarError::new(
                    ErrorKind::Internal,
                    format!("engine \"{id}\" declares op \"{name}\" twice"),
                ));
            }
            let deadline_ms = match raw_op.get("deadline_ms") {
                None => None,
                Some(value) => Some(value.as_u64().ok_or_else(|| {
                    SidecarError::new(
                        ErrorKind::Internal,
                        format!("op \"{name}\" has a non-integer deadline_ms"),
                    )
                })?),
            };
            ops.push(OpSpec { name, deadline_ms });
        }

        Ok(Self { value, id, ops })
    }

    pub fn op_names(&self) -> Vec<&str> {
        self.ops.iter().map(|op| op.name.as_str()).collect()
    }

    pub fn find_op(&self, name: &str) -> Option<&OpSpec> {
        self.ops.iter().find(|op| op.name == name)
    }

    pub fn bundle(&self) -> Value {
        json!({
            "protocol": PROTOCOL,
            "bundle": BUNDLE,
            "toolkit_version": HOST_VERSION,
            "binary_version": HOST_VERSION,
            "clients": [self.value.clone()],
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_duplicate_ops() {
        let value = json!({"id": "echo", "ops": [{"name": "echo"}, {"name": "echo"}]});
        assert!(Descriptor::parse(value).is_err());
    }

    #[test]
    fn parses_deadline_and_bundle() {
        let value = json!({
            "id": "echo",
            "ops": [{"name": "sleep", "deadline_ms": 5000}, {"name": "echo"}]
        });
        let descriptor = Descriptor::parse(value).unwrap();
        assert_eq!(descriptor.id, "echo");
        assert_eq!(descriptor.find_op("sleep").unwrap().deadline_ms, Some(5000));
        assert_eq!(descriptor.find_op("echo").unwrap().deadline_ms, None);
        assert_eq!(descriptor.bundle()["clients"][0]["id"], "echo");
    }
}
