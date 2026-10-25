//! Host SDK for aio_reverse sidecar engines (wire protocol v1).
//!
//! An engine only implements [`Engine`] and [`Session`]; [`run_stdio`] owns the
//! framing, base ops, sessions, deadlines, events and error serialization.

pub mod engine;
pub mod error;
pub mod host;
pub mod proto;
pub mod spec;

pub use engine::{Call, Engine, Session, SessionCtx};
pub use error::{ErrorKind, SidecarError};
pub use host::{run_stdio, HostOptions};
pub use proto::{canonical_json, fnv1a64, read_frame, schema_hash, write_frame};
pub use spec::{Descriptor, OpSpec, BASE_OPS, BUNDLE, HOST_VERSION, PROTOCOL};
