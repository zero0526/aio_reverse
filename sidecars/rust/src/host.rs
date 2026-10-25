//! Protocol v1 host: serial dispatch, sessions, deadlines and event routing.

use std::collections::HashMap;
use std::io;
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::{Duration, Instant};

use serde_json::{json, Value};

use crate::engine::{Call, CancelState, Engine, EventSink, SessionCtx};
use crate::error::{ErrorKind, SidecarError};
use crate::proto::{read_frame, schema_hash};
use crate::spec::{Descriptor, BASE_OPS, BUNDLE, HOST_VERSION, PROTOCOL};

#[derive(Debug, Clone)]
pub struct HostOptions {
    pub pid: u32,
}

impl Default for HostOptions {
    fn default() -> Self {
        Self {
            pid: std::process::id(),
        }
    }
}

enum Incoming {
    Frame { value: Value, bin: Vec<u8> },
    Eof,
    Fatal(String),
}

#[derive(Debug, Default)]
struct Metrics {
    requests: u64,
    calls: u64,
    errors: u64,
    sessions_opened: u64,
}

struct SessionEntry {
    id: String,
    target: String,
    session: Box<dyn crate::engine::Session>,
}

struct HostState<E: Engine> {
    engine: E,
    descriptor: Descriptor,
    schema_hash: String,
    sink: EventSink,
    cancel: Arc<CancelState>,
    sessions: HashMap<String, SessionEntry>,
    next_session: u64,
    metrics: Metrics,
    pid: u32,
    shutdown_requested: bool,
}

/// Serves protocol v1 over stdin/stdout until `shutdown` or EOF.
///
/// Requests are processed serially. A reader thread handles `cancel` frames
/// immediately by flipping a flag the engine observes through `Call::check`;
/// deadlines are also checked cooperatively and again after the call returns.
pub fn run_stdio<E: Engine>(engine: E, options: HostOptions) -> io::Result<()> {
    let descriptor = Descriptor::parse(engine.describe())
        .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err.to_string()))?;
    let schema_hash = schema_hash(&descriptor.value);
    let sink = EventSink::new(io::stdout());
    let cancel = Arc::new(CancelState::default());
    let (tx, rx) = mpsc::channel::<Incoming>();

    {
        let cancel = Arc::clone(&cancel);
        thread::Builder::new()
            .name("aio-sidecar-reader".to_string())
            .spawn(move || {
                let stdin = io::stdin();
                let mut reader = stdin.lock();
                loop {
                    match read_frame(&mut reader) {
                        Ok(Some((value, bin))) => {
                            if value.get("t").and_then(Value::as_str) == Some("cancel") {
                                if let Some(id) = value.get("id").and_then(Value::as_u64) {
                                    cancel.cancel(id);
                                }
                                continue;
                            }
                            if tx.send(Incoming::Frame { value, bin }).is_err() {
                                break;
                            }
                        }
                        Ok(None) => {
                            let _ = tx.send(Incoming::Eof);
                            break;
                        }
                        Err(err) => {
                            let _ = tx.send(Incoming::Fatal(err.to_string()));
                            break;
                        }
                    }
                }
            })?;
    }

    let mut host = HostState {
        engine,
        descriptor,
        schema_hash,
        sink,
        cancel,
        sessions: HashMap::new(),
        next_session: 1,
        metrics: Metrics::default(),
        pid: options.pid,
        shutdown_requested: false,
    };

    let mut result = Ok(());
    for incoming in rx {
        match incoming {
            Incoming::Frame { value, bin } => match host.handle_envelope(value, &bin) {
                Ok(true) => break,
                Ok(false) => {}
                Err(err) => {
                    result = Err(err);
                    break;
                }
            },
            Incoming::Eof => break,
            Incoming::Fatal(message) => {
                result = Err(io::Error::new(io::ErrorKind::InvalidData, message));
                break;
            }
        }
    }

    host.close_all();
    result
}

impl<E: Engine> HostState<E> {
    fn handle_envelope(&mut self, envelope: Value, bin: &[u8]) -> io::Result<bool> {
        if envelope.get("t").and_then(Value::as_str) != Some("req") {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unexpected envelope type {:?}", envelope.get("t")),
            ));
        }
        let id = envelope
            .get("id")
            .and_then(Value::as_u64)
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "request id must be an unsigned integer",
                )
            })?;
        self.metrics.requests += 1;

        if envelope.get("v").and_then(Value::as_u64) != Some(PROTOCOL) {
            self.respond_error(
                id,
                "",
                None,
                &SidecarError::new(
                    ErrorKind::Protocol,
                    format!("unsupported protocol version {:?}", envelope.get("v")),
                ),
            );
            return Ok(false);
        }

        let op = match envelope.get("op").and_then(Value::as_str) {
            Some(op) if !op.is_empty() => op.to_string(),
            _ => {
                self.respond_error(
                    id,
                    "",
                    None,
                    &SidecarError::new(ErrorKind::BadInput, "op must be a non-empty string"),
                );
                return Ok(false);
            }
        };

        let params = match envelope.get("params") {
            None => Value::Object(Default::default()),
            Some(Value::Object(map)) => Value::Object(map.clone()),
            Some(_) => {
                self.respond_error(
                    id,
                    &op,
                    None,
                    &bad_input("params must be a JSON object", &op),
                );
                return Ok(false);
            }
        };

        let session_id = match envelope.get("session") {
            None => None,
            Some(Value::String(session)) if !session.is_empty() => Some(session.clone()),
            Some(_) => {
                self.respond_error(
                    id,
                    &op,
                    None,
                    &bad_input("session must be a non-empty string", &op),
                );
                return Ok(false);
            }
        };

        let requested_deadline = match envelope.get("deadline_ms") {
            None => None,
            Some(value) => match value.as_u64() {
                Some(ms) => Some(ms),
                None => {
                    self.respond_error(
                        id,
                        &op,
                        None,
                        &bad_input("deadline_ms must be a non-negative integer", &op),
                    );
                    return Ok(false);
                }
            },
        };

        let target_hint = session_id
            .as_ref()
            .and_then(|session| self.sessions.get(session))
            .map(|entry| entry.target.clone());

        let deadline_ms = requested_deadline.or_else(|| {
            if BASE_OPS.contains(&op.as_str()) {
                None
            } else {
                self.descriptor
                    .find_op(&op)
                    .and_then(|spec| spec.deadline_ms)
                    .filter(|ms| *ms > 0)
            }
        });

        let deadline = match deadline_ms {
            None => None,
            Some(ms) => match Instant::now().checked_add(Duration::from_millis(ms)) {
                Some(deadline) => Some(deadline),
                None => {
                    self.respond_error(
                        id,
                        &op,
                        target_hint.as_deref(),
                        &bad_input("deadline_ms is too large", &op),
                    );
                    return Ok(false);
                }
            },
        };

        if self.cancel.begin(id) {
            self.respond_error(
                id,
                &op,
                target_hint.as_deref(),
                &SidecarError::new(
                    ErrorKind::Cancelled,
                    format!("op \"{op}\" was cancelled"),
                )
                .with_op(&op),
            );
            self.cancel.finish(id);
            return Ok(false);
        }

        let target_owned = target_hint.clone().unwrap_or_default();
        let mut call = Call::new(
            id,
            &op,
            &target_owned,
            bin,
            deadline,
            deadline_ms,
            Arc::clone(&self.cancel),
            self.sink.clone(),
        );

        let outcome = catch_unwind(AssertUnwindSafe(|| {
            self.dispatch(&op, session_id, params, &mut call)
        }));
        self.cancel.finish(id);

        match outcome {
            Ok(Ok(result)) => {
                let output = call.take_output();
                self.respond_result(id, result, output);
                Ok(self.shutdown_requested)
            }
            Ok(Err(error)) => {
                self.respond_error(id, &op, target_hint.as_deref(), &error);
                Ok(false)
            }
            Err(payload) => {
                let error = SidecarError::from_panic(payload);
                self.respond_error(id, &op, target_hint.as_deref(), &error);
                Ok(false)
            }
        }
    }

    fn dispatch(
        &mut self,
        op: &str,
        session_id: Option<String>,
        params: Value,
        call: &mut Call<'_>,
    ) -> Result<Value, SidecarError> {
        match op {
            "hello" => Ok(self.hello()),
            "describe" => Ok(self.descriptor.bundle()),
            "targets" => Ok(json!([self.descriptor.id.as_str()])),
            "metrics" => Ok(self.metrics_value()),
            "open" => self.open(params),
            "close" => self.close_session(session_id.as_deref(), op),
            "health" => self.health(session_id.as_deref(), op),
            "warmup" => self.warmup(session_id.as_deref(), op, call),
            "diag" => self.diag(session_id.as_deref(), op),
            "shutdown" => {
                self.close_all();
                self.shutdown_requested = true;
                Ok(json!({ "stopping": true }))
            }
            _ => self.target_op(op, session_id.as_deref(), params, call),
        }
    }

    fn hello(&self) -> Value {
        json!({
            "protocol": PROTOCOL,
            "bundle": BUNDLE,
            "binary_version": HOST_VERSION,
            "toolkit_version": HOST_VERSION,
            "schema_hash": self.schema_hash,
            "targets": [self.descriptor.id.as_str()],
            "workers": 1,
            "pid": self.pid,
        })
    }

    fn metrics_value(&self) -> Value {
        json!({
            "requests": self.metrics.requests,
            "calls": self.metrics.calls,
            "errors": self.metrics.errors,
            "events": self.sink.event_count(),
            "sessions_opened": self.metrics.sessions_opened,
            "sessions_open": self.sessions.len(),
        })
    }

    fn open(&mut self, params: Value) -> Result<Value, SidecarError> {
        let target = params
            .get("target")
            .and_then(Value::as_str)
            .filter(|target| !target.is_empty())
            .ok_or_else(|| bad_input("open requires a target string", "open"))?
            .to_string();
        if target != self.descriptor.id {
            return Err(SidecarError::new(
                ErrorKind::Unsupported,
                format!("unknown target \"{target}\""),
            )
            .with_op("open")
            .with_target(&target));
        }

        let config = params.get("config").cloned().unwrap_or_else(|| json!({}));
        let session = format!("s{}", self.next_session);
        self.next_session += 1;
        let ctx = SessionCtx {
            session: session.clone(),
            target: target.clone(),
            pid: self.pid,
        };
        let engine_session = self.engine.open(&ctx, config)?;
        self.metrics.sessions_opened += 1;
        let ops = self.descriptor.op_names();
        self.sessions.insert(
            session.clone(),
            SessionEntry {
                id: session.clone(),
                target: target.clone(),
                session: engine_session,
            },
        );
        Ok(json!({
            "session": session,
            "target": target,
            "worker": 0,
            "ops": ops,
        }))
    }

    fn close_session(
        &mut self,
        session_id: Option<&str>,
        op: &str,
    ) -> Result<Value, SidecarError> {
        let session_id = session_id
            .ok_or_else(|| bad_input(format!("op \"{op}\" requires a session"), op))?;
        let mut entry = self.sessions.remove(session_id).ok_or_else(|| {
            SidecarError::new(
                ErrorKind::BadInput,
                format!("unknown session \"{session_id}\""),
            )
            .with_op(op)
        })?;
        entry.session.close()?;
        Ok(json!({ "closed": true }))
    }

    fn health(&mut self, session_id: Option<&str>, op: &str) -> Result<Value, SidecarError> {
        self.session_entry(session_id, op)?.session.health()
    }

    fn warmup(
        &mut self,
        session_id: Option<&str>,
        op: &str,
        call: &mut Call<'_>,
    ) -> Result<Value, SidecarError> {
        self.session_entry(session_id, op)?.session.warmup(call)?;
        Ok(json!({ "warm": true }))
    }

    fn diag(&mut self, session_id: Option<&str>, op: &str) -> Result<Value, SidecarError> {
        let entry = self.session_entry(session_id, op)?;
        let report = entry.session.diagnostics();
        Ok(json!({
            "target": entry.target.clone(),
            "session": entry.id.clone(),
            "mode": "off",
            "path": Value::Null,
            "report": report,
        }))
    }

    fn target_op(
        &mut self,
        op: &str,
        session_id: Option<&str>,
        params: Value,
        call: &mut Call<'_>,
    ) -> Result<Value, SidecarError> {
        let session_id = session_id
            .ok_or_else(|| bad_input(format!("op \"{op}\" requires a session"), op))?
            .to_string();
        let entry = self.sessions.get_mut(&session_id).ok_or_else(|| {
            SidecarError::new(
                ErrorKind::BadInput,
                format!("unknown session \"{session_id}\""),
            )
            .with_op(op)
        })?;

        if self.descriptor.find_op(op).is_none() {
            return Err(SidecarError::new(
                ErrorKind::Unsupported,
                format!(
                    "op \"{op}\" is not declared by target \"{}\"",
                    entry.target
                ),
            )
            .with_op(op)
            .with_target(entry.target.clone()));
        }

        self.metrics.calls += 1;
        let result = entry.session.call(op, params, call)?;

        if call.cancelled() {
            return Err(SidecarError::new(
                ErrorKind::Cancelled,
                format!("op \"{op}\" was cancelled"),
            )
            .with_op(op)
            .with_target(entry.target.clone()));
        }
        if call.timed_out() {
            return Err(SidecarError::new(
                ErrorKind::Timeout,
                format!(
                    "op \"{op}\" exceeded its deadline of {}ms",
                    call.deadline_ms().unwrap_or(0)
                ),
            )
            .with_op(op)
            .with_target(entry.target.clone()));
        }
        Ok(result)
    }

    fn session_entry<'a>(
        &'a mut self,
        session_id: Option<&str>,
        op: &str,
    ) -> Result<&'a mut SessionEntry, SidecarError> {
        let session_id = session_id
            .ok_or_else(|| bad_input(format!("op \"{op}\" requires a session"), op))?;
        self.sessions.get_mut(session_id).ok_or_else(|| {
            SidecarError::new(
                ErrorKind::BadInput,
                format!("unknown session \"{session_id}\""),
            )
            .with_op(op)
        })
    }

    fn respond_result(&mut self, id: u64, result: Value, bin: Vec<u8>) {
        let envelope = json!({
            "t": "res",
            "v": PROTOCOL,
            "id": id,
            "ok": true,
            "result": result,
        });
        self.sink.send(&envelope, &bin);
    }

    fn respond_error(
        &mut self,
        id: u64,
        op: &str,
        target: Option<&str>,
        error: &SidecarError,
    ) {
        self.metrics.errors += 1;
        let op = if op.is_empty() { None } else { Some(op) };
        let envelope = json!({
            "t": "res",
            "v": PROTOCOL,
            "id": id,
            "ok": false,
            "error": error.to_wire(target, op),
        });
        self.sink.send(&envelope, &[]);
    }

    fn close_all(&mut self) {
        let mut sessions: Vec<SessionEntry> =
            self.sessions.drain().map(|(_, entry)| entry).collect();
        for entry in &mut sessions {
            let _ = entry.session.close();
        }
    }
}

fn bad_input(message: impl Into<String>, op: &str) -> SidecarError {
    SidecarError::new(ErrorKind::BadInput, message).with_op(op)
}
