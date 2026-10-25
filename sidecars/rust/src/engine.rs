//! Engine/session traits and the per-call handle.

use std::collections::HashSet;
use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

use serde::Serialize;
use serde_json::{json, Value};

use crate::error::{ErrorKind, SidecarError};
use crate::proto::write_frame;

#[derive(Debug, Clone, Serialize)]
pub struct SessionCtx {
    pub session: String,
    pub target: String,
    pub pid: u32,
}

/// One engine per process. `describe` returns the v1 descriptor subset;
/// `open` builds the per-session state.
pub trait Engine {
    fn describe(&self) -> Value;

    fn open(&self, ctx: &SessionCtx, config: Value) -> Result<Box<dyn Session>, SidecarError>;
}

/// Per-session engine state. Only `call` is required.
pub trait Session {
    fn call(
        &mut self,
        op: &str,
        params: Value,
        call: &mut Call<'_>,
    ) -> Result<Value, SidecarError>;

    fn health(&mut self) -> Result<Value, SidecarError> {
        Ok(json!({ "ok": true }))
    }

    fn warmup(&mut self, _call: &mut Call<'_>) -> Result<(), SidecarError> {
        Ok(())
    }

    fn diagnostics(&mut self) -> Value {
        Value::Null
    }

    fn close(&mut self) -> Result<(), SidecarError> {
        Ok(())
    }
}

#[derive(Debug, Default)]
struct CancelInner {
    current: Option<u64>,
    cancelled: bool,
    cancelled_ids: HashSet<u64>,
}

/// Shared with the reader thread so `cancel` flips the in-flight call.
#[derive(Debug, Default)]
pub(crate) struct CancelState {
    inner: Mutex<CancelInner>,
}

impl CancelState {
    pub(crate) fn cancel(&self, id: u64) {
        let mut inner = self.inner.lock().expect("cancel state poisoned");
        if inner.current == Some(id) {
            inner.cancelled = true;
        } else {
            inner.cancelled_ids.insert(id);
        }
    }

    pub(crate) fn begin(&self, id: u64) -> bool {
        let mut inner = self.inner.lock().expect("cancel state poisoned");
        inner.current = Some(id);
        inner.cancelled = inner.cancelled_ids.remove(&id);
        inner.cancelled
    }

    pub(crate) fn is_cancelled(&self, id: u64) -> bool {
        let inner = self.inner.lock().expect("cancel state poisoned");
        inner.current == Some(id) && inner.cancelled
    }

    pub(crate) fn finish(&self, id: u64) {
        let mut inner = self.inner.lock().expect("cancel state poisoned");
        if inner.current == Some(id) {
            inner.current = None;
            inner.cancelled = false;
        }
    }
}

/// Writes frames from the main thread and counts emitted events.
#[derive(Clone)]
pub(crate) struct EventSink {
    inner: Arc<Mutex<Box<dyn Write + Send>>>,
    events: Arc<AtomicU64>,
}

impl EventSink {
    pub(crate) fn new<W: Write + Send + 'static>(writer: W) -> Self {
        Self {
            inner: Arc::new(Mutex::new(Box::new(writer))),
            events: Arc::new(AtomicU64::new(0)),
        }
    }

    pub(crate) fn send(&self, envelope: &Value, bin: &[u8]) {
        let mut writer = self.inner.lock().expect("event sink poisoned");
        if let Err(err) = write_frame(&mut *writer, envelope, bin) {
            panic!("failed to write sidecar frame: {err}");
        }
    }

    pub(crate) fn send_event(&self, envelope: &Value, bin: &[u8]) {
        self.events.fetch_add(1, Ordering::Relaxed);
        self.send(envelope, bin);
    }

    pub(crate) fn event_count(&self) -> u64 {
        self.events.load(Ordering::Relaxed)
    }
}

/// The per-call handle passed to `Session::call`.
pub struct Call<'a> {
    id: u64,
    op: &'a str,
    target: &'a str,
    input: &'a [u8],
    output: Vec<u8>,
    deadline: Option<Instant>,
    deadline_ms: Option<u64>,
    cancel: Arc<CancelState>,
    sink: EventSink,
}

impl<'a> Call<'a> {
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn new(
        id: u64,
        op: &'a str,
        target: &'a str,
        input: &'a [u8],
        deadline: Option<Instant>,
        deadline_ms: Option<u64>,
        cancel: Arc<CancelState>,
        sink: EventSink,
    ) -> Self {
        Self {
            id,
            op,
            target,
            input,
            output: Vec::new(),
            deadline,
            deadline_ms,
            cancel,
            sink,
        }
    }

    /// Throws `timeout` / `cancelled`; call this between steps.
    pub fn check(&self) -> Result<(), SidecarError> {
        if self.cancelled() {
            return Err(self.located(SidecarError::new(
                ErrorKind::Cancelled,
                format!("op \"{}\" was cancelled", self.op),
            )));
        }
        if self.timed_out() {
            return Err(self.timeout_error());
        }
        Ok(())
    }

    pub fn cancelled(&self) -> bool {
        self.cancel.is_cancelled(self.id)
    }

    pub fn timed_out(&self) -> bool {
        self.deadline
            .map(|deadline| Instant::now() >= deadline)
            .unwrap_or(false)
    }

    pub fn deadline_ms(&self) -> Option<u64> {
        self.deadline_ms
    }

    /// Emits one event envelope before the response.
    pub fn emit(&mut self, name: &str, data: Value) {
        if name.is_empty() {
            panic!("event name must be a non-empty string");
        }
        let envelope = json!({
            "t": "evt",
            "v": 1,
            "id": self.id,
            "event": name,
            "data": data,
        });
        self.sink.send_event(&envelope, &[]);
    }

    pub fn log(&mut self, level: &str, text: &str) {
        self.emit("log", json!({ "level": level, "text": text }));
    }

    /// Raw binary frame part received with the request.
    pub fn input(&self) -> &[u8] {
        self.input
    }

    /// Sets the binary frame part of the response.
    pub fn set_output(&mut self, bytes: impl Into<Vec<u8>>) {
        self.output = bytes.into();
    }

    pub(crate) fn take_output(&mut self) -> Vec<u8> {
        std::mem::take(&mut self.output)
    }

    pub(crate) fn timeout_error(&self) -> SidecarError {
        self.located(SidecarError::new(
            ErrorKind::Timeout,
            format!(
                "op \"{}\" exceeded its deadline of {}ms",
                self.op,
                self.deadline_ms.unwrap_or(0)
            ),
        ))
    }

    fn located(&self, error: SidecarError) -> SidecarError {
        let error = error.with_op(self.op);
        if self.target.is_empty() {
            error
        } else {
            error.with_target(self.target)
        }
    }
}
