//! Sidecar error taxonomy and wire serialization.

use std::any::Any;
use std::fmt;

use serde_json::{json, Map, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ErrorKind {
    BadInput,
    Unsupported,
    TargetDrift,
    Blocked,
    Timeout,
    Cancelled,
    Resource,
    Protocol,
    Internal,
}

impl ErrorKind {
    pub const ALL: [ErrorKind; 9] = [
        ErrorKind::BadInput,
        ErrorKind::Unsupported,
        ErrorKind::TargetDrift,
        ErrorKind::Blocked,
        ErrorKind::Timeout,
        ErrorKind::Cancelled,
        ErrorKind::Resource,
        ErrorKind::Protocol,
        ErrorKind::Internal,
    ];

    pub fn as_str(self) -> &'static str {
        match self {
            ErrorKind::BadInput => "bad_input",
            ErrorKind::Unsupported => "unsupported",
            ErrorKind::TargetDrift => "target_drift",
            ErrorKind::Blocked => "blocked",
            ErrorKind::Timeout => "timeout",
            ErrorKind::Cancelled => "cancelled",
            ErrorKind::Resource => "resource",
            ErrorKind::Protocol => "protocol",
            ErrorKind::Internal => "internal",
        }
    }

    pub fn retryable(self) -> bool {
        matches!(
            self,
            ErrorKind::Blocked | ErrorKind::Timeout | ErrorKind::Resource
        )
    }

    pub fn parse(value: &str) -> Option<Self> {
        ErrorKind::ALL
            .into_iter()
            .find(|kind| kind.as_str() == value)
    }
}

#[derive(Debug, Clone)]
pub struct SidecarError {
    pub kind: ErrorKind,
    pub message: String,
    pub retryable: bool,
    pub target: Option<String>,
    pub op: Option<String>,
    pub detail: Option<Value>,
}

impl SidecarError {
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            retryable: kind.retryable(),
            target: None,
            op: None,
            detail: None,
        }
    }

    pub fn with_target(mut self, target: impl Into<String>) -> Self {
        self.target = Some(target.into());
        self
    }

    pub fn with_op(mut self, op: impl Into<String>) -> Self {
        self.op = Some(op.into());
        self
    }

    pub fn with_detail(mut self, detail: Value) -> Self {
        self.detail = Some(detail);
        self
    }

    pub fn with_retryable(mut self, retryable: bool) -> Self {
        self.retryable = retryable;
        self
    }

    pub fn from_panic(payload: Box<dyn Any + Send>) -> Self {
        let message = panic_message(payload.as_ref());
        Self::new(ErrorKind::Internal, format!("engine panicked: {message}")).with_detail(json!({
            "engine_exception": {
                "type": "panic",
                "message": message,
            }
        }))
    }

    pub fn to_wire(&self, fallback_target: Option<&str>, fallback_op: Option<&str>) -> Value {
        let mut wire = Map::new();
        wire.insert("kind".to_string(), json!(self.kind.as_str()));
        wire.insert("message".to_string(), json!(self.message));
        wire.insert("retryable".to_string(), json!(self.retryable));
        if let Some(target) = self.target.as_deref().or(fallback_target) {
            wire.insert("target".to_string(), json!(target));
        }
        if let Some(op) = self.op.as_deref().or(fallback_op) {
            wire.insert("op".to_string(), json!(op));
        }
        if let Some(detail) = &self.detail {
            wire.insert("detail".to_string(), detail.clone());
        }
        Value::Object(wire)
    }
}

impl fmt::Display for SidecarError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let location = match (&self.target, &self.op) {
            (Some(target), Some(op)) => format!(" in {target}.{op}"),
            (Some(target), None) => format!(" in {target}"),
            (None, Some(op)) => format!(" in {op}"),
            (None, None) => String::new(),
        };
        write!(f, "{}{location}: {}", self.kind.as_str(), self.message)
    }
}

impl std::error::Error for SidecarError {}

fn panic_message(payload: &dyn Any) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_string()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "engine panicked".to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retryable_defaults_match_the_contract() {
        for kind in ErrorKind::ALL {
            let expected = matches!(
                kind,
                ErrorKind::Blocked | ErrorKind::Timeout | ErrorKind::Resource
            );
            assert_eq!(kind.retryable(), expected, "{}", kind.as_str());
            assert_eq!(SidecarError::new(kind, "x").retryable, expected);
        }
    }

    #[test]
    fn wire_error_carries_fallbacks_and_detail() {
        let error = SidecarError::new(ErrorKind::Blocked, "challenge")
            .with_detail(json!({"status": 403}));
        let wire = error.to_wire(Some("echo"), Some("solve"));
        assert_eq!(wire["kind"], "blocked");
        assert_eq!(wire["retryable"], true);
        assert_eq!(wire["target"], "echo");
        assert_eq!(wire["op"], "solve");
        assert_eq!(wire["detail"]["status"], 403);
    }

    #[test]
    fn panic_reports_engine_exception() {
        let error = SidecarError::from_panic(Box::new("boom"));
        assert_eq!(error.kind, ErrorKind::Internal);
        assert_eq!(error.detail.unwrap()["engine_exception"]["type"], "panic");
    }
}
