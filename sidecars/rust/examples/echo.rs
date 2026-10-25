use std::time::{Duration, Instant};

use aio_sidecar::{
    run_stdio, Call, Engine, ErrorKind, HostOptions, Session, SessionCtx, SidecarError,
};
use serde_json::{json, Value};

const DESCRIPTOR: &str = include_str!("../../conformance/fixtures/echo.descriptor.json");

struct EchoEngine {
    descriptor: Value,
}

impl Engine for EchoEngine {
    fn describe(&self) -> Value {
        self.descriptor.clone()
    }

    fn open(&self, ctx: &SessionCtx, config: Value) -> Result<Box<dyn Session>, SidecarError> {
        Ok(Box::new(EchoSession {
            config,
            ctx: ctx.clone(),
            calls: 0,
            events: 0,
        }))
    }
}

struct EchoSession {
    config: Value,
    ctx: SessionCtx,
    calls: u64,
    events: u64,
}

impl Session for EchoSession {
    fn call(
        &mut self,
        op: &str,
        params: Value,
        call: &mut Call<'_>,
    ) -> Result<Value, SidecarError> {
        self.calls += 1;

        match op {
            "echo" => Ok(json!({
                "value": params.get("value").cloned().unwrap_or(Value::Null),
                "config": self.config.clone(),
            })),

            "execute" => execute(&params, call, op),

            "emit" => {
                let name = params
                    .get("event")
                    .and_then(Value::as_str)
                    .unwrap_or("progress");
                if name != "progress" && name != "log" {
                    return Err(bad_input("event must be progress or log", op));
                }
                let data = params
                    .get("data")
                    .cloned()
                    .unwrap_or_else(|| json!({ "note": "emitted" }));
                call.emit(name, data.clone());
                self.events += 1;
                Ok(json!({ "emitted": name, "data": data }))
            }

            "bytes" => {
                let input = call.input().to_vec();
                let size = input.len();
                let hex = hex_encode(&input);
                call.set_output(input);
                Ok(json!({ "size": size, "hex": hex }))
            }

            "fail" => {
                let kind = params
                    .get("kind")
                    .and_then(Value::as_str)
                    .ok_or_else(|| bad_input("fail requires an error kind", op))?;
                let kind = ErrorKind::parse(kind)
                    .ok_or_else(|| bad_input(format!("unknown error kind \"{kind}\""), op))?;
                let message = params
                    .get("message")
                    .and_then(Value::as_str)
                    .map(|value| value.to_string())
                    .unwrap_or_else(|| format!("echo {}", kind.as_str()));
                let mut error = SidecarError::new(kind, message).with_op(op);
                if let Some(detail) = params.get("detail") {
                    error = error.with_detail(detail.clone());
                }
                if let Some(retryable) = params.get("retryable").and_then(Value::as_bool) {
                    error = error.with_retryable(retryable);
                }
                Err(error)
            }

            "throw" => {
                let message = params
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or("echo engine exploded");
                panic!("{message}");
            }

            "sleep" => {
                let ms = match params.get("ms") {
                    None => 1000u64,
                    Some(value) => value
                        .as_u64()
                        .ok_or_else(|| bad_input("ms must be a non-negative integer", op))?,
                };
                let started = Instant::now();
                loop {
                    call.check()?;
                    let elapsed = started.elapsed().as_millis() as u64;
                    if elapsed >= ms {
                        break;
                    }
                    std::thread::sleep(Duration::from_millis((ms - elapsed).min(10)));
                }
                call.check()?;
                Ok(json!({ "slept_ms": started.elapsed().as_millis() as u64 }))
            }

            "stats" => Ok(json!({
                "calls": self.calls,
                "events": self.events,
                "config": self.config.clone(),
            })),

            _ => Err(SidecarError::new(
                ErrorKind::Unsupported,
                format!("op \"{op}\" is not implemented"),
            )
            .with_op(op)),
        }
    }

    fn health(&mut self) -> Result<Value, SidecarError> {
        Ok(json!({
            "ok": true,
            "target": self.ctx.target,
            "detail": { "calls": self.calls, "events": self.events },
        }))
    }

    fn warmup(&mut self, call: &mut Call<'_>) -> Result<(), SidecarError> {
        call.log("info", "echo engine warmed up");
        Ok(())
    }

    fn diagnostics(&mut self) -> Value {
        json!({
            "calls": self.calls,
            "events": self.events,
            "config": self.config.clone(),
            "context": self.ctx.clone(),
        })
    }

    fn close(&mut self) -> Result<(), SidecarError> {
        Ok(())
    }
}

fn execute(params: &Value, call: &Call<'_>, op: &str) -> Result<Value, SidecarError> {
    let entrypoint = params
        .get("entrypoint")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| bad_input("execute requires a non-empty entrypoint", op))?;
    let source_kind = params
        .get("source_kind")
        .and_then(Value::as_str)
        .filter(|value| *value == "text" || *value == "binary")
        .ok_or_else(|| bad_input("source_kind must be \"text\" or \"binary\"", op))?;
    let source = params.get("source").cloned().unwrap_or(Value::Null);
    match source_kind {
        "text" => {
            if !source.is_string() {
                return Err(bad_input("source must be a string for text sources", op));
            }
        }
        _ => {
            if !source.is_null() {
                return Err(bad_input("source must be null for binary sources", op));
            }
        }
    }
    let arguments = params
        .get("arguments")
        .cloned()
        .unwrap_or_else(|| json!([]));
    if !arguments.is_array() {
        return Err(bad_input("arguments must be an array", op));
    }
    let environment = params.get("environment").cloned().unwrap_or(Value::Null);
    let memory_limit = match params.get("memory_limit_mb") {
        None => 64,
        Some(value) => value
            .as_u64()
            .filter(|value| *value > 0)
            .ok_or_else(|| bad_input("memory_limit_mb must be a positive integer", op))?,
    };
    let input = call.input();
    let source_bytes = if source_kind == "binary" {
        input.len()
    } else {
        source.as_str().map(|text| text.len()).unwrap_or(0)
    };

    Ok(json!({
        "result": {
            "entrypoint": entrypoint,
            "arguments": arguments,
            "environment": environment,
            "source_kind": source_kind,
            "source": source,
            "memory_limit_mb": memory_limit,
        },
        "source_bytes": source_bytes,
    }))
}

fn bad_input(message: impl Into<String>, op: &str) -> SidecarError {
    SidecarError::new(ErrorKind::BadInput, message).with_op(op)
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        out.push(HEX[(byte >> 4) as usize] as char);
        out.push(HEX[(byte & 0x0f) as usize] as char);
    }
    out
}

fn main() {
    let descriptor: Value =
        serde_json::from_str(DESCRIPTOR).expect("echo descriptor fixture is valid JSON");
    if let Err(error) = run_stdio(EchoEngine { descriptor }, HostOptions::default()) {
        eprintln!("echo sidecar failed: {error}");
        std::process::exit(1);
    }
}
